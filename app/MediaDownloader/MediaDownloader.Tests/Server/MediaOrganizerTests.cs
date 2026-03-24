using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Core;

namespace MediaDownloader.Tests.Server;

public class MediaOrganizerTests : IDisposable
{
    private readonly string _tempDir;
    private readonly ServerSettings _settings;
    private readonly MediaOrganizer _organizer;

    public MediaOrganizerTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"Organizer_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);

        _settings = new ServerSettings
        {
            InstallDir = _tempDir,
            MoviesDir = Path.Combine(_tempDir, "Movies"),
            TvDir = Path.Combine(_tempDir, "TV Shows"),
            AnimeDir = Path.Combine(_tempDir, "Anime"),
            DownloadsDir = Path.Combine(_tempDir, "staging"),
        };
        Directory.CreateDirectory(_settings.MoviesDir);
        Directory.CreateDirectory(_settings.TvDir);
        Directory.CreateDirectory(_settings.AnimeDir);
        Directory.CreateDirectory(_settings.DownloadsDir);

        _organizer = new MediaOrganizer(_settings);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    [Fact]
    public void Organize_Movie_CreatesCorrectPath()
    {
        var source = Path.Combine(_settings.DownloadsDir, "inception.mkv");
        File.WriteAllBytes(source, new byte[100]);

        var media = new MediaInfo { Title = "Inception", Year = 2010, Type = "movie" };
        var result = _organizer.Organize(source, media);

        Assert.Contains("Inception (2010)", result);
        Assert.EndsWith(".mkv", result);
        Assert.True(File.Exists(result));
        Assert.False(File.Exists(source)); // moved
    }

    [Fact]
    public void Organize_Movie_NoYear()
    {
        var source = Path.Combine(_settings.DownloadsDir, "movie.mkv");
        File.WriteAllBytes(source, new byte[100]);

        var media = new MediaInfo { Title = "Unknown Movie", Type = "movie" };
        var result = _organizer.Organize(source, media);

        Assert.Contains("Unknown Movie", result);
        Assert.DoesNotContain("()", result);
    }

    [Fact]
    public void Organize_TvEpisode_CreatesPlexPath()
    {
        var source = Path.Combine(_settings.DownloadsDir, "episode.mkv");
        File.WriteAllBytes(source, new byte[100]);

        var media = new MediaInfo
        {
            Title = "Breaking Bad", Type = "tv",
            Season = 1, Episode = 3,
            EpisodeTitles = new() { [3] = "...And the Bag's in the River" },
        };
        var result = _organizer.Organize(source, media);

        Assert.Contains("Breaking Bad", result);
        Assert.Contains("Season 01", result);
        Assert.Contains("S01E03", result);
        Assert.Contains("And the Bag's in the River", result); // sanitized (dots/leading trimmed)
    }

    [Fact]
    public void Organize_Anime_UsesAnimeDir()
    {
        var source = Path.Combine(_settings.DownloadsDir, "ep01.mkv");
        File.WriteAllBytes(source, new byte[100]);

        var media = new MediaInfo
        {
            Title = "Attack on Titan", Type = "anime",
            Season = 1, Episode = 1,
        };
        var result = _organizer.Organize(source, media);

        Assert.StartsWith(_settings.AnimeDir, result);
    }

    [Fact]
    public void Organize_TvNoEpisode_KeepsOriginalFilename()
    {
        var source = Path.Combine(_settings.DownloadsDir, "My.Show.S01E05.720p.mkv");
        File.WriteAllBytes(source, new byte[100]);

        var media = new MediaInfo { Title = "My Show", Type = "tv", Season = 1 };
        var result = _organizer.Organize(source, media);

        Assert.Contains("Season 01", result);
        // Original filename kept (sanitized)
        Assert.Contains("My.Show.S01E05.720p.mkv", result);
    }
}
