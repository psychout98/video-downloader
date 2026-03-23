using System.Text.RegularExpressions;
using MediaDownloader.Server.Api.Models;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Core;

namespace MediaDownloader.Server.Api;

public static class LibraryEndpoints
{
    private static readonly string[] PosterNames = ["poster.jpg", "poster.png", "movie.jpg", "folder.jpg", "thumb.jpg", "cover.jpg"];
    private static readonly HashSet<string> VideoExts = [".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"];
    private static readonly Regex SxExRe = new(@"[Ss](\d{1,2})[Ee](\d{1,3})", RegexOptions.Compiled);
    private static readonly Regex SOnlyRe = new(@"[Ss]eason\s*(\d{1,2})|[Ss](\d{1,2})\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);

    public static void Map(WebApplication app)
    {
        app.MapGet("/api/library", (LibraryManager library, bool force = false) =>
        {
            var items = library.Scan(force);
            return Results.Ok(new { items, count = items.Count });
        });

        app.MapGet("/api/library/poster", (string path) =>
        {
            if (!File.Exists(path))
                return Results.NotFound(new { detail = "Poster not found" });
            var ext = Path.GetExtension(path).ToLowerInvariant();
            if (ext is not ".jpg" and not ".jpeg" and not ".png" and not ".webp")
                return Results.BadRequest(new { detail = "Not an image file" });
            return Results.File(path, ext switch
            {
                ".png" => "image/png",
                ".webp" => "image/webp",
                _ => "image/jpeg",
            });
        });

        app.MapGet("/api/library/poster/tmdb", async (
            string title, string folder, int? year, string type,
            TmdbClient tmdb, ServerSettings settings) =>
        {
            var postersDir = settings.PostersDir;

            string? CheckCached(string key)
            {
                var safe = Regex.Replace(key, @"[\\/:*?""<>|]", "_").Trim();
                foreach (var ext in new[] { ".jpg", ".png", ".jpeg", ".webp" })
                {
                    var p = Path.Combine(postersDir, safe + ext);
                    if (File.Exists(p)) return p;
                }
                return null;
            }

            var inputKey = year.HasValue ? $"{title} ({year})" : title;
            var folderName = Path.GetFileName(folder);
            foreach (var key in new[] { inputKey, folderName })
            {
                var hit = CheckCached(key);
                if (hit != null) return Results.File(hit, "image/jpeg");
            }

            // Legacy poster inside media folder
            foreach (var name in PosterNames)
            {
                var p = Path.Combine(folder, name);
                if (File.Exists(p)) return Results.File(p, "image/jpeg");
            }

            // Resolve via TMDB
            string canonicalTitle, posterPath;
            int? canonicalYear;
            try
            {
                (canonicalTitle, canonicalYear, posterPath) = await tmdb.FuzzyResolveAsync(title, type, year);
            }
            catch (Exception ex) { return Results.NotFound(new { detail = ex.Message }); }
            if (posterPath == null)
                return Results.NotFound(new { detail = "No poster available on TMDB" });

            // Download
            byte[] posterData;
            try
            {
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
                posterData = await http.GetByteArrayAsync($"https://image.tmdb.org/t/p/w500{posterPath}");
            }
            catch (Exception ex) { return Results.NotFound(new { detail = $"Poster download failed: {ex.Message}" }); }

            // Cache
            var canonicalKey = canonicalYear.HasValue ? $"{canonicalTitle} ({canonicalYear})" : canonicalTitle;
            try
            {
                Directory.CreateDirectory(postersDir);
                var safeKey = Regex.Replace(canonicalKey, @"[\\/:*?""<>|]", "_").Trim();
                File.WriteAllBytes(Path.Combine(postersDir, $"{safeKey}.jpg"), posterData);
            }
            catch { }

            return Results.Bytes(posterData, "image/jpeg");
        });

        app.MapPost("/api/library/refresh", async (TmdbClient tmdb, LibraryManager library, CancellationToken ct) =>
            Results.Ok(await library.RefreshAsync(tmdb, ct)));

        app.MapGet("/api/library/episodes", (string folder, string? folder_archive, ProgressStore? progressStore) =>
        {
            if (!Directory.Exists(folder))
                return Results.NotFound(new { detail = "Show folder not found" });

            var dirsToScan = new List<string> { folder };
            if (folder_archive != null && Directory.Exists(folder_archive) &&
                Path.GetFullPath(folder_archive) != Path.GetFullPath(folder))
                dirsToScan.Add(folder_archive);

            var seasons = new Dictionary<int, List<Dictionary<string, object?>>>();
            var seenFilenames = new HashSet<string>();

            foreach (var scanDir in dirsToScan)
            {
                foreach (var video in Directory.EnumerateFiles(scanDir, "*", SearchOption.AllDirectories).OrderBy(f => f))
                {
                    if (!VideoExts.Contains(Path.GetExtension(video).ToLowerInvariant())) continue;
                    var name = Path.GetFileName(video);
                    if (!seenFilenames.Add(name)) continue;

                    var stem = Path.GetFileNameWithoutExtension(video);
                    int season, episode;
                    string epTitle;
                    var m = SxExRe.Match(stem);
                    if (m.Success)
                    {
                        season = int.Parse(m.Groups[1].Value);
                        episode = int.Parse(m.Groups[2].Value);
                        epTitle = stem[(m.Index + m.Length)..].Trim(' ', '-', '–');
                    }
                    else
                    {
                        var ms = SOnlyRe.Match(Path.GetFileName(Path.GetDirectoryName(video) ?? ""));
                        season = ms.Success ? int.Parse(ms.Groups[1].Success ? ms.Groups[1].Value : ms.Groups[2].Value) : 1;
                        episode = 0;
                        epTitle = stem;
                    }

                    var progress = progressStore?.Get(video);
                    int pct = 0;
                    if (progress != null && progress.ContainsKey("duration_ms"))
                    {
                        var dur = Convert.ToInt64(progress["duration_ms"]);
                        if (dur > 0)
                            pct = (int)Math.Round(Math.Min((double)Convert.ToInt64(progress["position_ms"]) / dur, 1.0) * 100);
                    }

                    if (!seasons.ContainsKey(season)) seasons[season] = [];
                    seasons[season].Add(new()
                    {
                        ["season"] = season, ["episode"] = episode, ["title"] = epTitle,
                        ["filename"] = name, ["path"] = video,
                        ["size_bytes"] = new FileInfo(video).Length,
                        ["progress_pct"] = pct,
                        ["position_ms"] = progress?.GetValueOrDefault("position_ms") ?? 0,
                        ["duration_ms"] = progress?.GetValueOrDefault("duration_ms") ?? 0,
                    });
                }
            }

            foreach (var eps in seasons.Values)
                eps.Sort((a, b) =>
                {
                    var c = ((int)(a["episode"] ?? 0)).CompareTo((int)(b["episode"] ?? 0));
                    return c != 0 ? c : string.Compare(a["filename"]?.ToString(), b["filename"]?.ToString(), StringComparison.Ordinal);
                });

            return Results.Ok(new
            {
                seasons = seasons.OrderBy(kv => kv.Key).Select(kv => new
                {
                    season = kv.Key,
                    episodes = kv.Value,
                }).ToArray(),
            });
        });

        app.MapGet("/api/progress", (string path, ProgressStore? progressStore) =>
            Results.Ok(progressStore?.Get(path) ?? new Dictionary<string, object>()));

        app.MapPost("/api/progress", (ProgressUpdateRequest body, ProgressStore? progressStore) =>
        {
            progressStore?.Save(body.Path, body.PositionMs, body.DurationMs);
            return Results.Ok(new { ok = true });
        });
    }
}
