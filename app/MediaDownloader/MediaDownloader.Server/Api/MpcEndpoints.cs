using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;
using MediaDownloader.Server.Api.Models;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Core;

namespace MediaDownloader.Server.Api;

public static class MpcEndpoints
{
    private static readonly Regex EpRe = new(@"[Ss](\d+)[Ee](\d+)", RegexOptions.Compiled);
    private static readonly HashSet<string> VideoExts = [".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv", ".m4v"];

    public static void Map(WebApplication app)
    {
        app.MapGet("/api/mpc/status", async (MpcClient mpc, LibraryManager library) =>
        {
            var status = await mpc.GetStatusAsync();
            var result = status.ToDict();
            result["media"] = StripWindowsPaths(ResolveMediaContext(status.File, library));
            return Results.Ok(result);
        });

        app.MapPost("/api/mpc/command", async (MpcCommandRequest body, MpcClient mpc) =>
        {
            var extra = body.PositionMs.HasValue
                ? new Dictionary<string, string> { ["position"] = body.PositionMs.Value.ToString() }
                : null;
            var ok = await mpc.CommandAsync(body.Command, extra);
            return Results.Ok(new { ok });
        });

        app.MapPost("/api/mpc/open", async (MpcOpenRequest body, MpcClient mpc, ServerSettings settings) =>
        {
            var resolved = ResolveEpisodePath(body.TmdbId, body.RelPath, settings);
            if (resolved == null)
                return Results.NotFound(new { detail = $"File not found: tmdb_id={body.TmdbId}, rel_path={body.RelPath}" });

            var exe = settings.MpcBeExe;
            if (!File.Exists(exe))
                return Results.Problem($"MPC-BE executable not found at '{exe}'.");

            string openPath;
            if (body.Playlist != null && body.Playlist.Count > 1)
            {
                var playlistPaths = body.Playlist.Select(rel =>
                {
                    var p = ResolveEpisodePath(body.TmdbId, rel, settings);
                    return p ?? rel;
                }).ToList();
                openPath = MakePlaylist(playlistPaths, settings);
            }
            else
            {
                openPath = resolved;
            }

            var wasRunning = await mpc.PingAsync();
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = exe,
                    Arguments = $"\"{openPath}\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                });
            }
            catch (Exception ex) { return Results.Problem($"Failed to launch MPC-BE: {ex.Message}"); }

            return Results.Ok(new { ok = true, launched = !wasRunning });
        });

        app.MapPost("/api/mpc/next", async (MpcClient mpc) =>
        {
            var status = await mpc.GetStatusAsync();
            if (string.IsNullOrEmpty(status.File))
                return Results.NotFound(new { detail = "Nothing is currently playing" });
            var (target, rel) = FindAdjacentEpisode(status.File, +1);
            if (target == null) return Results.NotFound(new { detail = "No next episode found" });
            return Results.Ok(new { ok = true, rel_path = rel, path = target });
        });

        app.MapPost("/api/mpc/prev", async (MpcClient mpc) =>
        {
            var status = await mpc.GetStatusAsync();
            if (string.IsNullOrEmpty(status.File))
                return Results.NotFound(new { detail = "Nothing is currently playing" });
            var (target, rel) = FindAdjacentEpisode(status.File, -1);
            if (target == null) return Results.NotFound(new { detail = "No previous episode found" });
            return Results.Ok(new { ok = true, rel_path = rel, path = target });
        });

        app.MapGet("/api/mpc/stream", async (MpcClient mpc, LibraryManager library, HttpContext ctx, int limit = 0) =>
        {
            ctx.Response.ContentType = "text/event-stream";
            ctx.Response.Headers["Cache-Control"] = "no-cache";
            ctx.Response.Headers["X-Accel-Buffering"] = "no";

            int count = 0;
            while (!ctx.RequestAborted.IsCancellationRequested)
            {
                try
                {
                    var status = await mpc.GetStatusAsync(ctx.RequestAborted);
                    var result = status.ToDict();
                    result["media"] = StripWindowsPaths(ResolveMediaContext(status.File, library));
                    await ctx.Response.WriteAsync($"data:{JsonSerializer.Serialize(result)}\n\n", ctx.RequestAborted);
                    await ctx.Response.Body.FlushAsync(ctx.RequestAborted);
                }
                catch (OperationCanceledException) { break; }
                catch
                {
                    await ctx.Response.WriteAsync(
                        $"data:{JsonSerializer.Serialize(new { reachable = false, state = 0, media = (object?)null })}\n\n",
                        ctx.RequestAborted);
                    await ctx.Response.Body.FlushAsync(ctx.RequestAborted);
                }
                count++;
                if (limit > 0 && count >= limit) break;
                await Task.Delay(1000, ctx.RequestAborted);
            }
        });
    }

    private static Dictionary<string, object?>? ResolveMediaContext(string filePath, LibraryManager library)
    {
        if (string.IsNullOrEmpty(filePath)) return null;
        var items = library.Scan();
        foreach (var item in items)
        {
            var folderName = item.GetValueOrDefault("folder_name")?.ToString() ?? "";
            if (!string.IsNullOrEmpty(folderName) && filePath.Contains(folderName))
            {
                int? season = null, episode = null;
                var m = EpRe.Match(filePath);
                if (m.Success) { season = int.Parse(m.Groups[1].Value); episode = int.Parse(m.Groups[2].Value); }

                string? posterUrl = null;
                if (item.GetValueOrDefault("poster") is string poster)
                    posterUrl = $"/api/library/poster?path={poster}";

                return new()
                {
                    ["tmdb_id"] = item.GetValueOrDefault("tmdb_id"),
                    ["title"] = item.GetValueOrDefault("title"),
                    ["type"] = item.GetValueOrDefault("type"),
                    ["poster_url"] = posterUrl,
                    ["season"] = season,
                    ["episode"] = episode,
                };
            }
        }
        return null;
    }

    private static object? StripWindowsPaths(Dictionary<string, object?>? media)
    {
        if (media == null) return null;
        return media.ToDictionary(kv => kv.Key,
            kv => kv.Value is string s && Regex.IsMatch(s, @"^[A-Z]:\\") ? null : kv.Value);
    }

    private static string? ResolveEpisodePath(int tmdbId, string relPath, ServerSettings settings)
    {
        var folder = FindLibraryFolder(tmdbId, settings);
        if (folder == null) return null;
        var full = Path.Combine(folder, relPath);
        if (File.Exists(full)) return full;
        foreach (var f in Directory.EnumerateFiles(folder, Path.GetFileName(relPath), SearchOption.AllDirectories))
            if (File.Exists(f)) return f;
        return null;
    }

    private static string? FindLibraryFolder(int tmdbId, ServerSettings settings)
    {
        var searchDirs = new[] { settings.MoviesDir, settings.TvDir, settings.AnimeDir,
            settings.MoviesDirArchive, settings.TvDirArchive, settings.AnimeDirArchive };
        foreach (var d in searchDirs)
        {
            if (!Directory.Exists(d)) continue;
            foreach (var folder in Directory.EnumerateDirectories(d))
                if (Path.GetFileName(folder).Contains($"[{tmdbId}]"))
                    return folder;
        }
        return null;
    }

    private static (string? path, string? rel) FindAdjacentEpisode(string currentFile, int offset)
    {
        string? showFolder = null;
        var dir = Path.GetDirectoryName(currentFile);
        while (dir != null)
        {
            if (Regex.IsMatch(Path.GetFileName(dir), @"\[\d+\]"))
            {
                showFolder = dir;
                break;
            }
            dir = Path.GetDirectoryName(dir);
        }
        showFolder ??= Path.GetDirectoryName(Path.GetDirectoryName(currentFile));
        if (showFolder == null || !Directory.Exists(showFolder)) return (null, null);

        var episodes = Directory.EnumerateFiles(showFolder, "*", SearchOption.AllDirectories)
            .Where(f => VideoExts.Contains(Path.GetExtension(f).ToLowerInvariant()) && EpRe.IsMatch(Path.GetFileName(f)))
            .OrderBy(f => f)
            .ToList();
        if (episodes.Count == 0) return (null, null);

        var currentIdx = episodes.FindIndex(ep =>
            Path.GetFullPath(ep) == Path.GetFullPath(currentFile) || Path.GetFileName(ep) == Path.GetFileName(currentFile));
        if (currentIdx < 0) return (null, null);

        var targetIdx = currentIdx + offset;
        if (targetIdx < 0 || targetIdx >= episodes.Count) return (null, null);

        var target = episodes[targetIdx];
        var rel = Path.GetRelativePath(showFolder, target);
        return (target, rel);
    }

    private static string MakePlaylist(List<string> files, ServerSettings settings)
    {
        var playlistFile = Path.Combine(settings.DataDir, "current_playlist.m3u");
        Directory.CreateDirectory(Path.GetDirectoryName(playlistFile)!);
        File.WriteAllText(playlistFile, "#EXTM3U\n" + string.Join("\n", files) + "\n",
            System.Text.Encoding.UTF8);
        return playlistFile;
    }
}
