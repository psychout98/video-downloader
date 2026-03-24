using System.Text.RegularExpressions;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Server.Core;

/// <summary>
/// Moves downloaded files into the library in Plex-compatible paths.
/// Mirrors server/core/media_organizer.py.
/// </summary>
public class MediaOrganizer
{
    private static readonly Regex IllegalChars = new(@"[<>:""/\\|?*\x00-\x1f]", RegexOptions.Compiled);
    private static readonly Regex MultiSpace = new(@"\s{2,}", RegexOptions.Compiled);
    private static readonly HashSet<string> VideoExtensions = [".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv"];

    private readonly ServerSettings _settings;
    private readonly ILogger? _logger;

    public MediaOrganizer(ServerSettings settings, ILogger? logger = null)
    {
        _settings = settings;
        _logger = logger;
    }

    public string Organize(string sourcePath, MediaInfo media)
    {
        var source = new FileInfo(sourcePath);
        string videoFilePath;

        if (Directory.Exists(sourcePath))
        {
            videoFilePath = PickVideoFile(sourcePath) ?? throw new FileNotFoundException($"No video file found in {sourcePath}");
        }
        else
        {
            videoFilePath = sourcePath;
        }

        var dest = GetDestination(videoFilePath, media);
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);

        _logger?.LogInformation("Moving {Source} → {Dest}", videoFilePath, dest);
        File.Move(videoFilePath, dest, overwrite: false);

        // Clean up empty staging folders
        if (Directory.Exists(sourcePath) && sourcePath != Path.GetDirectoryName(videoFilePath))
        {
            try { Directory.Delete(sourcePath, recursive: true); } catch { }
        }

        return dest;
    }

    private string GetDestination(string videoFile, MediaInfo media)
    {
        var ext = Path.GetExtension(videoFile).ToLowerInvariant();
        if (string.IsNullOrEmpty(ext)) ext = ".mkv";
        var baseDir = GetBaseDir(media);

        if (media.Type == "movie")
        {
            var folderName = Sanitize(media.Year.HasValue ? $"{media.Title} ({media.Year})" : media.Title);
            var fileName = Sanitize(media.Year.HasValue ? $"{media.Title} ({media.Year}){ext}" : $"{media.Title}{ext}");
            return Path.Combine(baseDir, folderName, fileName);
        }

        // TV / Anime
        var showDir = Sanitize(media.Title);
        var seasonNum = media.Season ?? 1;
        var seasonDir = $"Season {seasonNum:D2}";

        string fileName2;
        if (media.Episode.HasValue)
        {
            var epTitle = media.EpisodeTitles.GetValueOrDefault(media.Episode.Value, "");
            var epSuffix = !string.IsNullOrEmpty(epTitle) ? $" - {Sanitize(epTitle)}" : "";
            fileName2 = Sanitize($"{media.Title} - S{seasonNum:D2}E{media.Episode:D2}{epSuffix}{ext}");
        }
        else
        {
            // Season pack — keep original filename
            fileName2 = Sanitize(Path.GetFileNameWithoutExtension(videoFile) + ext);
        }

        return Path.Combine(baseDir, showDir, seasonDir, fileName2);
    }

    private string GetBaseDir(MediaInfo media) => media.Type switch
    {
        "anime" => _settings.AnimeDir,
        "tv" => _settings.TvDir,
        _ => _settings.MoviesDir,
    };

    private static string Sanitize(string name)
    {
        name = IllegalChars.Replace(name, "");
        return MultiSpace.Replace(name, " ").Trim(' ', '.');
    }

    private static string? PickVideoFile(string directory)
    {
        string? best = null;
        long bestSize = 0;

        foreach (var file in Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories))
        {
            if (!VideoExtensions.Contains(Path.GetExtension(file).ToLowerInvariant()))
                continue;
            var size = new FileInfo(file).Length;
            if (size > bestSize)
            {
                bestSize = size;
                best = file;
            }
        }
        return best;
    }
}
