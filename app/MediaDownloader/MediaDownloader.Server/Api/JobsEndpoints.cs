using System.Collections.Concurrent;
using System.Text.Json;
using MediaDownloader.Server.Api.Models;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Core;
using MediaDownloader.Server.Data;

namespace MediaDownloader.Server.Api;

public static class JobsEndpoints
{
    private const int MaxSearchCache = 50;
    private const int SearchTtl = 300;

    // In-memory search cache
    private static readonly ConcurrentDictionary<string, SearchEntry> Searches = new();

    private record SearchEntry(
        Dictionary<string, object?> Media,
        List<Dictionary<string, object?>> Streams,
        long ExpiresAt);

    public static void Map(WebApplication app)
    {
        app.MapPost("/api/search", async (
            SearchRequest body,
            TmdbClient tmdb,
            TorrentioClient torrentio,
            JobProcessor processor) =>
        {
            if (string.IsNullOrWhiteSpace(body.Query))
                return Results.UnprocessableEntity(new { detail = "query must not be empty" });

            PruneSearches();

            // 1. TMDB lookup
            MediaInfo media;
            try { media = await tmdb.SearchAsync(body.Query.Trim()); }
            catch (Exception ex) { return Results.NotFound(new { detail = $"TMDB search failed: {ex.Message}" }); }

            // 2. Streams from Torrentio
            var streams = new List<StreamResult>();
            string? streamWarning = null;

            try
            {
                var cached = await torrentio.GetStreamsAsync(media, cachedOnly: true);
                streams.AddRange(cached);
                if (cached.Count == 0)
                {
                    var all = await torrentio.GetStreamsAsync(media, cachedOnly: false);
                    streams.AddRange(all);
                }
            }
            catch (HttpRequestException ex) when (ex.StatusCode == System.Net.HttpStatusCode.Forbidden)
            {
                streamWarning = "Real-Debrid API key rejected (403 Forbidden). Please verify your key in Settings.";
            }
            catch (Exception ex)
            {
                streamWarning = $"Stream fetch failed: {ex.Message}";
            }

            if (streams.Count == 0 && streamWarning == null)
                streamWarning = $"No torrents found for '{media.DisplayName}'. Try a different query.";

            var searchId = Guid.NewGuid().ToString();
            var streamDicts = streams.Take(20).Select((s, idx) => new Dictionary<string, object?>
            {
                ["index"] = idx, ["name"] = s.Name, ["info_hash"] = s.InfoHash,
                ["download_url"] = s.DownloadUrl, ["size_bytes"] = s.SizeBytes,
                ["seeders"] = s.Seeders, ["is_cached_rd"] = s.IsCachedRd,
                ["magnet"] = s.Magnet, ["file_idx"] = s.FileIdx,
            }).ToList();

            var mediaDict = new Dictionary<string, object?>
            {
                ["title"] = media.Title, ["year"] = media.Year, ["imdb_id"] = media.ImdbId,
                ["tmdb_id"] = media.TmdbId, ["type"] = media.Type, ["season"] = media.Season,
                ["episode"] = media.Episode, ["is_anime"] = media.IsAnime,
                ["episode_titles"] = media.EpisodeTitles, ["overview"] = media.Overview,
                ["poster_path"] = media.PosterPath, ["poster_url"] = media.PosterUrl,
            };

            Searches[searchId] = new SearchEntry(mediaDict, streamDicts,
                DateTimeOffset.UtcNow.ToUnixTimeSeconds() + SearchTtl);

            return Results.Ok(new
            {
                search_id = searchId,
                media = mediaDict,
                streams = streamDicts,
                warning = streamWarning,
            });
        });

        app.MapPost("/api/download", async (DownloadRequest body, DbService db) =>
        {
            if (!Searches.TryGetValue(body.SearchId, out var cached))
                return Results.NotFound(new { detail = "Search session expired — please search again" });
            if (body.StreamIndex >= cached.Streams.Count)
                return Results.UnprocessableEntity(new { detail = "stream_index out of range" });

            var streamD = cached.Streams[body.StreamIndex];
            var mediaD = cached.Media;
            var title = mediaD["title"]?.ToString() ?? "Unknown";

            var streamDataJson = JsonSerializer.Serialize(new { media = mediaD, stream = streamD });
            var job = await db.CreateJobAsync(
                $"{title} (user-selected stream #{body.StreamIndex})", streamDataJson);

            await db.UpdateJobAsync(job["id"]!.ToString()!, new()
            {
                ["title"] = mediaD["title"],
                ["year"] = mediaD["year"] ?? DBNull.Value,
                ["imdb_id"] = mediaD["imdb_id"] ?? DBNull.Value,
                ["type"] = mediaD["type"],
                ["season"] = mediaD["season"] ?? DBNull.Value,
                ["episode"] = mediaD["episode"] ?? DBNull.Value,
                ["torrent_name"] = (streamD["name"]?.ToString() ?? "")[..Math.Min(120, (streamD["name"]?.ToString() ?? "").Length)],
            });

            return Results.Created($"/api/jobs/{job["id"]}", new
            {
                job_id = job["id"], status = "pending", message = $"Queued: {title}",
            });
        });

        app.MapGet("/api/jobs", async (DbService db) =>
            Results.Ok(new { jobs = await db.GetAllJobsAsync(200) }));

        app.MapGet("/api/jobs/{jobId}", async (string jobId, DbService db) =>
        {
            var job = await db.GetJobAsync(jobId);
            return job != null ? Results.Ok(job) : Results.NotFound(new { detail = "Job not found" });
        });

        app.MapDelete("/api/jobs/{jobId}", async (string jobId, DbService db, JobProcessor processor) =>
        {
            var job = await db.GetJobAsync(jobId);
            if (job == null) return Results.NotFound(new { detail = "Job not found" });

            processor.CancelJob(jobId);
            var status = job["status"]?.ToString() ?? "";
            if (JobStatus.Terminal.Contains(status))
            {
                await db.DeleteJobAsync(jobId);
                return Results.Ok(new { message = "Job deleted" });
            }
            await db.UpdateJobAsync(jobId, new() { ["status"] = JobStatus.Cancelled });
            return Results.Ok(new { message = "Job cancelled" });
        });

        app.MapPost("/api/jobs/{jobId}/retry", async (string jobId, DbService db) =>
        {
            var job = await db.GetJobAsync(jobId);
            if (job == null) return Results.NotFound(new { detail = "Job not found" });
            var status = job["status"]?.ToString() ?? "";
            if (status != JobStatus.Failed && status != JobStatus.Cancelled)
                return Results.BadRequest(new { detail = "Only failed/cancelled jobs can be retried" });
            await db.UpdateJobAsync(jobId, new()
            {
                ["status"] = JobStatus.Pending, ["error"] = (object)DBNull.Value,
                ["progress"] = 0.0, ["downloaded_bytes"] = 0, ["log"] = "",
            });
            return Results.Ok(new { message = "Job re-queued" });
        });
    }

    private static void PruneSearches()
    {
        var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        foreach (var (key, entry) in Searches)
        {
            if (entry.ExpiresAt < now)
                Searches.TryRemove(key, out _);
        }
        // Enforce size cap
        while (Searches.Count >= MaxSearchCache)
        {
            var oldest = Searches.OrderBy(kv => kv.Value.ExpiresAt).FirstOrDefault();
            if (oldest.Key != null) Searches.TryRemove(oldest.Key, out _);
            else break;
        }
    }
}
