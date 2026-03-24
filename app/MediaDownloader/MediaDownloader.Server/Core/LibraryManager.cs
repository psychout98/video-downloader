using System.Text.Json;
using System.Text.RegularExpressions;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Server.Core;

/// <summary>
/// Unified library scanner + normalizer + poster refresh.
/// Mirrors server/core/library_manager.py.
/// </summary>
public class LibraryManager
{
    private static readonly HashSet<string> VideoExtensions = [".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv", ".m4v"];
    private static readonly Regex ParenYear = new(@"^(.+?)\s*\((\d{4})\)\s*$", RegexOptions.Compiled);
    private static readonly Regex DotYear = new(@"^(.+?)[\.\s_](\d{4})(?:[\.\s_]|$)", RegexOptions.Compiled);
    private static readonly Regex DashYear = new(@"^(.+?)\s+-\s+(\d{4})\s*$", RegexOptions.Compiled);
    private static readonly Regex Quality = new(
        @"\b(2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|web-dl|webrip|remux|hevc|x265|x264|hdr|dv|atmos)\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private readonly (string primary, string archive, string type)[] _dirs;
    private readonly int _ttl;
    private readonly string _postersDir;
    private readonly string _libraryJsonPath;
    private readonly ILogger? _logger;

    private List<Dictionary<string, object?>> _cache = [];
    private double _cacheTime;

    public LibraryManager(ServerSettings settings, ILogger? logger = null)
    {
        _dirs =
        [
            (settings.MoviesDir, settings.MoviesDirArchive, "movie"),
            (settings.TvDir, settings.TvDirArchive, "tv"),
            (settings.AnimeDir, settings.AnimeDirArchive, "anime"),
        ];
        _ttl = 60;
        _postersDir = settings.PostersDir;
        _libraryJsonPath = Path.Combine(settings.DataDir, "library.json");
        _logger = logger;
    }

    public List<Dictionary<string, object?>> Scan(bool force = false)
    {
        if (!force && (Environment.TickCount64 / 1000.0 - _cacheTime) < _ttl)
            return _cache;

        var results = new List<Dictionary<string, object?>>();
        foreach (var (primary, archive, type) in _dirs)
        {
            var primaryItems = ScanDirectory(primary, type, "new");
            var archiveItems = ScanDirectory(archive, type, "archive");
            results.AddRange(MergeEntries(primaryItems, archiveItems, type));
        }

        results.Sort((a, b) =>
        {
            var ma = a.GetValueOrDefault("modified_at") as long? ?? 0;
            var mb = b.GetValueOrDefault("modified_at") as long? ?? 0;
            return mb.CompareTo(ma);
        });

        _cache = results;
        _cacheTime = Environment.TickCount64 / 1000.0;

        // Persist to library.json
        try
        {
            var dir = Path.GetDirectoryName(_libraryJsonPath);
            if (dir != null) Directory.CreateDirectory(dir);
            var tmp = _libraryJsonPath + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true }));
            File.Move(tmp, _libraryJsonPath, overwrite: true);
        }
        catch (Exception ex) { _logger?.LogWarning("Could not write library.json: {Error}", ex.Message); }

        _logger?.LogInformation("Library scan: {Count} items", results.Count);
        return results;
    }

    public async Task<Dictionary<string, object?>> RefreshAsync(TmdbClient tmdbClient, CancellationToken ct = default)
    {
        Directory.CreateDirectory(_postersDir);

        int renamedCount = 0, postersFetched = 0;
        var errors = new List<string>();

        foreach (var (primary, archive, type) in _dirs)
        {
            foreach (var libDir in new[] { primary, archive })
            {
                if (!Directory.Exists(libDir)) continue;

                foreach (var entry in Directory.EnumerateDirectories(libDir).OrderBy(d => d))
                {
                    var dirName = Path.GetFileName(entry);
                    if (dirName.StartsWith('.')) continue;

                    var hasVideo = Directory.EnumerateFiles(entry, "*", SearchOption.AllDirectories)
                        .Any(f => VideoExtensions.Contains(Path.GetExtension(f).ToLowerInvariant()));
                    if (!hasVideo) continue;

                    var (parsedTitle, parsedYear) = ExtractTitleYear(dirName);
                    await Task.Delay(250, ct); // Rate limit

                    string canonicalTitle;
                    int? canonicalYear;
                    string? posterPath;
                    try
                    {
                        (canonicalTitle, canonicalYear, posterPath) = await tmdbClient.FuzzyResolveAsync(
                            parsedTitle, type, parsedYear, ct);
                    }
                    catch (Exception ex)
                    {
                        errors.Add($"{dirName}: TMDB miss — {ex.Message}");
                        continue;
                    }

                    canonicalYear ??= parsedYear;
                    var newName = SafeFolder(canonicalYear.HasValue ? $"{canonicalTitle} ({canonicalYear})" : canonicalTitle);
                    var wasRenamed = false;

                    if (newName != dirName)
                    {
                        var newPath = Path.Combine(Path.GetDirectoryName(entry)!, newName);
                        if (Directory.Exists(newPath))
                        {
                            errors.Add($"Skip rename '{dirName}' → '{newName}': destination exists");
                        }
                        else
                        {
                            try
                            {
                                Directory.Move(entry, newPath);
                                renamedCount++;
                                wasRenamed = true;
                            }
                            catch (Exception ex) { errors.Add($"Rename failed '{dirName}': {ex.Message}"); }
                        }
                    }

                    // Smart poster refresh
                    var posterKey = wasRenamed ? newName : dirName;
                    var safeKey = SafePosterKey(posterKey);
                    var existingPoster = FindPoster(_postersDir, posterKey);

                    if ((existingPoster == null || wasRenamed) && posterPath != null)
                    {
                        try
                        {
                            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
                            var data = await http.GetByteArrayAsync($"https://image.tmdb.org/t/p/w500{posterPath}", ct);
                            File.WriteAllBytes(Path.Combine(_postersDir, $"{safeKey}.jpg"), data);
                            postersFetched++;
                        }
                        catch (Exception ex) { errors.Add($"Poster download failed for '{posterKey}': {ex.Message}"); }
                    }
                }
            }
        }

        Scan(force: true);

        return new()
        {
            ["renamed"] = renamedCount,
            ["posters_fetched"] = postersFetched,
            ["errors"] = errors,
            ["total_items"] = _cache.Count,
        };
    }

    // ------------------------------------------------------------------
    // Private helpers
    // ------------------------------------------------------------------

    private List<Dictionary<string, object?>> ScanDirectory(string baseDir, string mediaType, string storage)
    {
        var results = new List<Dictionary<string, object?>>();
        if (!Directory.Exists(baseDir)) return results;

        foreach (var entry in Directory.EnumerateFileSystemEntries(baseDir).OrderBy(e => e))
        {
            try
            {
                var name = Path.GetFileName(entry);
                if (name.StartsWith('.')) continue;

                if (Directory.Exists(entry))
                {
                    var (title, year) = ExtractTitleYear(name);
                    var videoFiles = Directory.EnumerateFiles(entry, "*", SearchOption.AllDirectories)
                        .Where(f => VideoExtensions.Contains(Path.GetExtension(f).ToLowerInvariant()))
                        .OrderBy(f => f)
                        .ToList();
                    if (videoFiles.Count == 0) continue;
                    var totalSize = videoFiles.Sum(f => new FileInfo(f).Length);
                    var titleKey = year.HasValue ? $"{title} ({year})" : title;
                    var poster = FindPoster(_postersDir, titleKey);

                    results.Add(new()
                    {
                        ["title"] = title, ["year"] = year, ["type"] = mediaType,
                        ["path"] = videoFiles[0], ["folder"] = entry,
                        ["file_count"] = videoFiles.Count, ["size_bytes"] = totalSize,
                        ["poster"] = poster, ["modified_at"] = new DateTimeOffset(Directory.GetLastWriteTime(entry)).ToUnixTimeSeconds(),
                        ["storage"] = storage,
                    });
                }
                else if (File.Exists(entry) && VideoExtensions.Contains(Path.GetExtension(entry).ToLowerInvariant()))
                {
                    var (title, year) = ExtractTitleYear(Path.GetFileNameWithoutExtension(entry));
                    var titleKey = year.HasValue ? $"{title} ({year})" : title;
                    var poster = FindPoster(_postersDir, titleKey);
                    var fi = new FileInfo(entry);

                    results.Add(new()
                    {
                        ["title"] = title, ["year"] = year, ["type"] = mediaType,
                        ["path"] = entry, ["folder"] = Path.GetDirectoryName(entry),
                        ["file_count"] = 1, ["size_bytes"] = fi.Length,
                        ["poster"] = poster, ["modified_at"] = new DateTimeOffset(fi.LastWriteTime).ToUnixTimeSeconds(),
                        ["storage"] = storage,
                    });
                }
            }
            catch (Exception ex) { _logger?.LogWarning("Error scanning {Entry}: {Error}", entry, ex.Message); }
        }
        return results;
    }

    private static List<Dictionary<string, object?>> MergeEntries(
        List<Dictionary<string, object?>> primary, List<Dictionary<string, object?>> archive, string mediaType)
    {
        if (mediaType == "movie")
            return [.. primary, .. archive];

        var byTitle = new Dictionary<string, Dictionary<string, object?>>(StringComparer.OrdinalIgnoreCase);
        foreach (var item in primary)
            byTitle[item["title"]?.ToString() ?? ""] = new(item);

        foreach (var item in archive)
        {
            var key = item["title"]?.ToString() ?? "";
            if (byTitle.TryGetValue(key, out var existing))
            {
                existing["file_count"] = (int)(existing["file_count"] ?? 0) + (int)(item["file_count"] ?? 0);
                existing["size_bytes"] = (long)(existing["size_bytes"] ?? 0L) + (long)(item["size_bytes"] ?? 0L);
                existing["storage"] = "mixed";
                existing["modified_at"] = Math.Max((long)(existing["modified_at"] ?? 0L), (long)(item["modified_at"] ?? 0L));
                existing["poster"] ??= item["poster"];
                existing["folder_archive"] = item["folder"];
            }
            else
            {
                byTitle[key] = new(item);
            }
        }
        return [.. byTitle.Values];
    }

    internal static (string title, int? year) ExtractTitleYear(string name)
    {
        foreach (var pattern in new[] { ParenYear, DashYear })
        {
            var m = pattern.Match(name);
            if (m.Success)
                return (CleanTitle(m.Groups[1].Value), int.Parse(m.Groups[2].Value));
        }
        var dm = DotYear.Match(name);
        if (dm.Success)
            return (CleanTitle(dm.Groups[1].Value), int.Parse(dm.Groups[2].Value));
        return (CleanTitle(name), null);
    }

    private static string CleanTitle(string raw)
    {
        if (raw.Contains('.') && !raw.Contains(' '))
            raw = raw.Replace('.', ' ');
        raw = raw.Replace('_', ' ');
        raw = Quality.Replace(raw, "");
        raw = Regex.Replace(raw, @"\[.*?\]|\(.*?\)", "");
        return Regex.Replace(raw, @"\s{2,}", " ").Trim(' ', '.', '-');
    }

    private static string? FindPoster(string postersDir, string titleKey)
    {
        var safe = SafePosterKey(titleKey);
        foreach (var ext in new[] { ".jpg", ".png", ".jpeg", ".webp" })
        {
            var p = Path.Combine(postersDir, safe + ext);
            if (File.Exists(p)) return p;
        }
        return null;
    }

    internal static string SafePosterKey(string s) => Regex.Replace(s, @"[\\/:*?""<>|]", "_").Trim();
    private static string SafeFolder(string name)
    {
        name = Regex.Replace(name, @":\s*", " - ");
        name = Regex.Replace(name, @"[\\/*?""<>|]", "");
        return name.Trim(' ', '.');
    }
}
