using System.Text.Json;
using System.Text.RegularExpressions;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Data;

namespace MediaDownloader.Server.Core;

/// <summary>
/// Background job processor — polls for pending jobs and runs the download pipeline.
/// Mirrors server/core/job_processor.py.
/// </summary>
public class JobProcessor : BackgroundService
{
    private static readonly HashSet<string> VideoExts = [".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"];
    private const int PollInterval = 5;
    private const int MaxDownloadSeconds = 2 * 60 * 60;

    private readonly DbService _db;
    private readonly ServerSettings _settings;
    private readonly ILogger<JobProcessor> _logger;
    private readonly SemaphoreSlim _sem;
    private readonly HashSet<string> _active = [];
    private readonly object _activeLock = new();

    // Mutable references — updated when settings change
    public TmdbClient? Tmdb { get; set; }
    public TorrentioClient? Torrentio { get; set; }
    public RealDebridClient? Rd { get; set; }

    public JobProcessor(DbService db, ServerSettings settings, ILogger<JobProcessor> logger)
    {
        _db = db;
        _settings = settings;
        _logger = logger;
        _sem = new SemaphoreSlim(settings.MaxConcurrentDownloads);
    }

    public bool CancelJob(string jobId)
    {
        // Jobs run as fire-and-forget tasks; cancellation is done via DB status check in the pipeline
        return false;
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        _logger.LogInformation("JobProcessor started");
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var pending = await _db.GetPendingJobsAsync();
                foreach (var job in pending)
                {
                    var jid = job["id"]?.ToString() ?? "";
                    bool shouldStart;
                    lock (_activeLock) { shouldStart = _active.Add(jid); }
                    if (shouldStart)
                    {
                        _ = Task.Run(async () =>
                        {
                            try { await ProcessJobAsync(jid, ct); }
                            finally { lock (_activeLock) { _active.Remove(jid); } }
                        }, ct);
                    }
                }
            }
            catch (Exception ex) { _logger.LogError(ex, "Error in job poll loop"); }
            await Task.Delay(TimeSpan.FromSeconds(PollInterval), ct);
        }
    }

    private async Task ProcessJobAsync(string jobId, CancellationToken ct)
    {
        await _sem.WaitAsync(ct);
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(MaxDownloadSeconds));
            await RunPipelineAsync(jobId, cts.Token);
        }
        catch (OperationCanceledException)
        {
            await _db.UpdateJobAsync(jobId, new() { ["status"] = JobStatus.Cancelled });
            await LogAsync(jobId, "Job cancelled");
            await CleanupStagingAsync(jobId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Job {JobId} failed", jobId[..8]);
            await _db.UpdateJobAsync(jobId, new() { ["status"] = JobStatus.Failed, ["error"] = ex.Message });
            await LogAsync(jobId, $"ERROR: {ex.Message}");
            await CleanupStagingAsync(jobId);
        }
        finally { _sem.Release(); }
    }

    private async Task CleanupStagingAsync(string jobId)
    {
        if (!Directory.Exists(_settings.DownloadsDir)) return;
        foreach (var f in Directory.EnumerateFiles(_settings.DownloadsDir))
        {
            if (Path.GetFileName(f).Contains(jobId[..8]))
            {
                try { File.Delete(f); } catch { }
            }
        }
    }

    private async Task RunPipelineAsync(string jobId, CancellationToken ct)
    {
        var job = await _db.GetJobAsync(jobId);
        if (job == null) return;

        var streamDataStr = job["stream_data"]?.ToString();
        if (string.IsNullOrEmpty(streamDataStr))
            throw new InvalidOperationException("No stream selected — job requires a pre-selected stream from the UI");

        var sd = JsonSerializer.Deserialize<JsonElement>(streamDataStr);
        var mediaD = sd.GetProperty("media");
        var streamD = sd.GetProperty("stream");

        var media = new MediaInfo
        {
            Title = GetStr(mediaD, "title") ?? "",
            Year = GetInt(mediaD, "year"),
            ImdbId = GetStr(mediaD, "imdb_id"),
            TmdbId = GetInt(mediaD, "tmdb_id"),
            Type = GetStr(mediaD, "type") ?? "movie",
            Season = GetInt(mediaD, "season"),
            Episode = GetInt(mediaD, "episode"),
            IsAnime = mediaD.TryGetProperty("is_anime", out var ia) && ia.GetBoolean(),
            PosterPath = GetStr(mediaD, "poster_path"),
        };

        // Parse episode titles
        if (mediaD.TryGetProperty("episode_titles", out var et) && et.ValueKind == JsonValueKind.Object)
        {
            foreach (var prop in et.EnumerateObject())
            {
                if (int.TryParse(prop.Name, out var epNum))
                    media.EpisodeTitles[epNum] = prop.Value.GetString() ?? "";
            }
        }

        var best = new StreamResult
        {
            Name = GetStr(streamD, "name") ?? "",
            InfoHash = GetStr(streamD, "info_hash"),
            DownloadUrl = GetStr(streamD, "download_url"),
            SizeBytes = GetLong(streamD, "size_bytes"),
            Seeders = GetInt(streamD, "seeders") ?? 0,
            IsCachedRd = streamD.TryGetProperty("is_cached_rd", out var cr) && cr.GetBoolean(),
            Magnet = GetStr(streamD, "magnet"),
            FileIdx = GetInt(streamD, "file_idx"),
        };

        await _db.UpdateJobAsync(jobId, new()
        {
            ["title"] = media.Title, ["year"] = (object?)media.Year ?? DBNull.Value,
            ["imdb_id"] = (object?)media.ImdbId ?? DBNull.Value, ["type"] = media.Type,
            ["season"] = (object?)media.Season ?? DBNull.Value, ["episode"] = (object?)media.Episode ?? DBNull.Value,
            ["torrent_name"] = best.Name.Length > 120 ? best.Name[..120] : best.Name,
            ["status"] = JobStatus.Found,
        });
        await LogAsync(jobId, $"Starting: {media.DisplayName}");
        await LogAsync(jobId, $"Stream: {(best.Name.Length > 80 ? best.Name[..80] : best.Name)}");

        var downloadFiles = await ResolveRdFilesAsync(jobId, best, media, ct);

        Directory.CreateDirectory(_settings.DownloadsDir);
        await DownloadAndOrganizeAsync(jobId, downloadFiles, media, ct);
    }

    private async Task<List<(string url, long? size)>> ResolveRdFilesAsync(
        string jobId, StreamResult best, MediaInfo media, CancellationToken ct)
    {
        var isSeasonPack = media.Type is "tv" or "anime" && !media.Episode.HasValue;

        if (best.IsCachedRd && best.DownloadUrl != null && !isSeasonPack)
        {
            await LogAsync(jobId, "Using pre-resolved RD URL (instant cache)");
            return [(best.DownloadUrl, best.SizeBytes)];
        }

        var magnet = best.Magnet ?? (best.InfoHash != null ? $"magnet:?xt=urn:btih:{best.InfoHash}" : null);
        if (magnet == null) throw new InvalidOperationException("No magnet link available for this stream");

        await _db.UpdateJobAsync(jobId, new() { ["status"] = JobStatus.AddingToRd });
        await LogAsync(jobId, "Adding to Real-Debrid ...");
        var torrentId = await Rd!.AddMagnetAsync(magnet, ct);
        await Rd.SelectAllFilesAsync(torrentId, ct);
        await _db.UpdateJobAsync(jobId, new() { ["rd_torrent_id"] = torrentId, ["status"] = JobStatus.WaitingForRd });
        await LogAsync(jobId, $"Waiting for RD (id={torrentId}) ...");

        var rdLinks = await Rd.WaitUntilDownloadedAsync(torrentId, async pct =>
        {
            await LogAsync(jobId, $"RD progress: {pct}%");
            await _db.UpdateJobAsync(jobId, new() { ["progress"] = pct / 100.0 * 0.3 });
        }, ct: ct);

        await LogAsync(jobId, $"RD ready -- unrestricting {rdLinks.Count} link(s) ...");
        var unrestricted = await Rd.UnrestrictAllAsync(rdLinks, ct);

        if (isSeasonPack)
        {
            var videoFiles = unrestricted
                .Where(x => IsVideoUrl(x.url) || (x.size ?? 0) > 50 * 1024 * 1024)
                .ToList();
            var files = videoFiles.Count > 0 ? videoFiles : unrestricted;
            files.Sort((a, b) => string.Compare(
                a.url.Split('?')[0].Split('/')[^1],
                b.url.Split('?')[0].Split('/')[^1],
                StringComparison.OrdinalIgnoreCase));
            await LogAsync(jobId, $"Season pack: {files.Count} episode file(s)");
            return files;
        }

        unrestricted.Sort((a, b) => (b.size ?? 0).CompareTo(a.size ?? 0));
        return [unrestricted[0]];
    }

    private async Task DownloadAndOrganizeAsync(
        string jobId, List<(string url, long? size)> files, MediaInfo media, CancellationToken ct)
    {
        var totalSize = files.Sum(f => f.size ?? 0);
        await _db.UpdateJobAsync(jobId, new()
        {
            ["status"] = JobStatus.Downloading,
            ["size_bytes"] = totalSize > 0 ? totalSize : (object)DBNull.Value,
        });

        string? lastFinalPath = null;
        var organizer = new MediaOrganizer(_settings, _logger);

        for (int i = 0; i < files.Count; i++)
        {
            var (dlUrl, flSize) = files[i];
            var fileName = FilenameFromUrl(dlUrl) ?? $"{jobId}_{i}.mkv";
            var stagingPath = Path.Combine(_settings.DownloadsDir, fileName);

            var prefix = files.Count > 1 ? $"[{i + 1}/{files.Count}] " : "";
            await LogAsync(jobId, $"{prefix}Downloading: {fileName}");
            await DownloadFileAsync(jobId, dlUrl, stagingPath, flSize, ct);

            // For season packs, detect episode number from filename
            var epMedia = media;
            if (!media.Episode.HasValue && media.Type is "tv" or "anime")
            {
                var epNum = EpisodeFromFilename(fileName);
                if (epNum.HasValue) epMedia = media.WithEpisode(epNum);
            }

            await _db.UpdateJobAsync(jobId, new() { ["status"] = JobStatus.Organizing });
            var finalPath = organizer.Organize(stagingPath, epMedia);
            await LogAsync(jobId, $"Organised -> {finalPath}");
            lastFinalPath = finalPath;
        }

        if (lastFinalPath != null)
        {
            await _db.UpdateJobAsync(jobId, new()
            {
                ["status"] = JobStatus.Complete,
                ["file_path"] = lastFinalPath,
                ["progress"] = 1.0,
                ["downloaded_bytes"] = totalSize > 0 ? totalSize : (object)DBNull.Value,
            });
            await LogAsync(jobId, $"Done ({files.Count} file(s))");
            await SavePosterAsync(media);
        }
    }

    private async Task DownloadFileAsync(
        string jobId, string url, string dest, long? totalSize, CancellationToken ct, int maxRetries = 3)
    {
        long downloaded = 0;
        Exception? lastExc = null;

        for (int attempt = 0; attempt < maxRetries; attempt++)
        {
            try
            {
                using var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = true })
                    { Timeout = Timeout.InfiniteTimeSpan };
                using var response = await client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct);
                response.EnsureSuccessStatusCode();

                if (response.Content.Headers.ContentLength.HasValue)
                {
                    totalSize = response.Content.Headers.ContentLength.Value;
                    await _db.UpdateJobAsync(jobId, new() { ["size_bytes"] = totalSize });
                }

                await using var stream = await response.Content.ReadAsStreamAsync(ct);
                await using var fileStream = new FileStream(dest, FileMode.Create, FileAccess.Write, FileShare.None, _settings.ChunkSize);
                var buffer = new byte[_settings.ChunkSize];

                while (true)
                {
                    var read = await stream.ReadAsync(buffer, ct);
                    if (read == 0) break;
                    await fileStream.WriteAsync(buffer.AsMemory(0, read), ct);
                    downloaded += read;

                    var pct = totalSize > 0 ? 0.3 + (double)downloaded / totalSize.Value * 0.7 : 0.5;
                    await _db.UpdateJobAsync(jobId, new()
                    {
                        ["downloaded_bytes"] = downloaded,
                        ["progress"] = Math.Min(pct, 0.99),
                    });
                }

                await LogAsync(jobId, $"Download complete: {downloaded / (1024.0 * 1024 * 1024):F2} GB");
                return;
            }
            catch (HttpRequestException ex)
            {
                lastExc = ex;
                var delay = 2 * (int)Math.Pow(2, attempt);
                await LogAsync(jobId, $"Download connect failed (attempt {attempt + 1}/{maxRetries}) — retrying in {delay}s");
                await Task.Delay(TimeSpan.FromSeconds(delay), ct);
            }
        }

        throw lastExc!;
    }

    private async Task SavePosterAsync(MediaInfo media)
    {
        if (media.PosterUrl == null) return;

        Directory.CreateDirectory(_settings.PostersDir);
        var key = media.Type == "movie"
            ? (media.Year.HasValue ? $"{media.Title} ({media.Year})" : media.Title)
            : media.Title;
        var safeKey = Regex.Replace(key, @"[\\/:*?""<>|]", "_").Trim();
        var posterFile = Path.Combine(_settings.PostersDir, $"{safeKey}.jpg");
        if (File.Exists(posterFile)) return;

        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
            var data = await client.GetByteArrayAsync(media.PosterUrl);
            await File.WriteAllBytesAsync(posterFile, data);
            _logger.LogInformation("Saved poster -> {File}", posterFile);
        }
        catch (Exception ex) { _logger.LogWarning("Could not download poster: {Error}", ex.Message); }
    }

    private async Task LogAsync(string jobId, string msg)
    {
        _logger.LogInformation("[job {Id}] {Msg}", jobId[..8], msg);
        await _db.AppendLogAsync(jobId, msg);
    }

    // ------------------------------------------------------------------
    // Static helpers
    // ------------------------------------------------------------------

    private static string? FilenameFromUrl(string url)
    {
        try
        {
            var path = url.Split('?')[0].TrimEnd('/');
            var name = Uri.UnescapeDataString(path.Split('/')[^1]);
            name = Regex.Replace(name, @"[?&=].*", "");
            return !string.IsNullOrEmpty(name) && name.Contains('.') ? name : null;
        }
        catch { return null; }
    }

    private static bool IsVideoUrl(string url)
    {
        var name = url.Split('?')[0].TrimEnd('/').Split('/')[^1].ToLowerInvariant();
        return VideoExts.Any(name.EndsWith);
    }

    internal static int? EpisodeFromFilename(string name)
    {
        var m = Regex.Match(name, @"[Ss]\d{1,2}[Ee](\d{1,3})");
        if (m.Success) return int.Parse(m.Groups[1].Value);
        m = Regex.Match(name, @"(?:^|[\s._-])[Ee]p?(\d{1,3})(?:[\s._\-\[]|$)");
        if (m.Success) return int.Parse(m.Groups[1].Value);
        m = Regex.Match(name, @"\s-\s(\d{1,3})\s-\s");
        if (m.Success) return int.Parse(m.Groups[1].Value);
        m = Regex.Match(name, @"\s-\s(\d{1,3})(?:\.\w{3}$|\s*\[)");
        if (m.Success) return int.Parse(m.Groups[1].Value);
        return null;
    }

    private static string? GetStr(JsonElement el, string prop) =>
        el.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
    private static int? GetInt(JsonElement el, string prop) =>
        el.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : null;
    private static long? GetLong(JsonElement el, string prop) =>
        el.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt64() : null;
}
