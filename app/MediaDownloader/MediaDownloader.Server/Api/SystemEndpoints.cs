using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Server.Api;

public static class SystemEndpoints
{
    public static void Map(WebApplication app)
    {
        app.MapGet("/api/status", (ServerSettings settings) => Results.Ok(new
        {
            status = "ok",
            movies_dir = settings.MoviesDir,
            tv_dir = settings.TvDir,
            anime_dir = settings.AnimeDir,
            movies_dir_archive = settings.MoviesDirArchive,
            tv_dir_archive = settings.TvDirArchive,
            anime_dir_archive = settings.AnimeDirArchive,
            watch_threshold_pct = (int)(settings.WatchThreshold * 100),
            mpc_be_url = settings.MpcBeUrl,
        }));

        app.MapGet("/api/logs", (ServerSettings settings, int lines = 200) =>
        {
            if (!File.Exists(settings.LogFile))
                return Results.Ok(new { lines = Array.Empty<string>(), note = "No log file found." });

            try
            {
                var allLines = File.ReadAllLines(settings.LogFile);
                var tail = allLines.Skip(Math.Max(0, allLines.Length - lines)).Select(l => l.TrimEnd()).ToArray();
                return Results.Ok(new { lines = tail, total = allLines.Length });
            }
            catch (Exception ex)
            {
                return Results.Problem($"Could not read log: {ex.Message}");
            }
        });
    }
}
