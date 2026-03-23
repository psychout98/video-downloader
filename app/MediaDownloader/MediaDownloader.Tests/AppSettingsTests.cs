using MediaDownloader.Models;

namespace MediaDownloader.Tests;

public class AppSettingsTests
{
    [Fact]
    public void DefaultValues_AreCorrect()
    {
        var settings = new AppSettings();

        Assert.Equal("", settings.TmdbApiKey);
        Assert.Equal("", settings.RealDebridApiKey);
        Assert.Equal("0.0.0.0", settings.Host);
        Assert.Equal(8000, settings.Port);
        Assert.Equal(2, settings.MaxConcurrentDownloads);
        Assert.Equal(0.85, settings.WatchThreshold);
        Assert.Equal("http://127.0.0.1:13579", settings.MpcBeUrl);
    }

    [Fact]
    public void ToDictionary_ContainsAllManagedKeys()
    {
        var settings = new AppSettings
        {
            TmdbApiKey = "tmdb123",
            RealDebridApiKey = "rd456",
            MoviesDir = "/movies",
            TvDir = "/tv",
            AnimeDir = "/anime",
            Host = "localhost",
            Port = 9000,
            MaxConcurrentDownloads = 5,
            WatchThreshold = 0.9,
        };

        var dict = settings.ToDictionary();

        Assert.Equal("tmdb123", dict["TMDB_API_KEY"]);
        Assert.Equal("rd456", dict["REAL_DEBRID_API_KEY"]);
        Assert.Equal("/movies", dict["MOVIES_DIR"]);
        Assert.Equal("/tv", dict["TV_DIR"]);
        Assert.Equal("/anime", dict["ANIME_DIR"]);
        Assert.Equal("localhost", dict["HOST"]);
        Assert.Equal("9000", dict["PORT"]);
        Assert.Equal("5", dict["MAX_CONCURRENT_DOWNLOADS"]);
        Assert.Equal("0.9", dict["WATCH_THRESHOLD"]);
    }

    [Fact]
    public void LoadFromDictionary_SetsStringProperties()
    {
        var settings = new AppSettings();
        var dict = new Dictionary<string, string>
        {
            ["TMDB_API_KEY"] = "my_key",
            ["MOVIES_DIR"] = "/path/to/movies",
            ["HOST"] = "127.0.0.1",
        };

        settings.LoadFromDictionary(dict);

        Assert.Equal("my_key", settings.TmdbApiKey);
        Assert.Equal("/path/to/movies", settings.MoviesDir);
        Assert.Equal("127.0.0.1", settings.Host);
    }

    [Fact]
    public void LoadFromDictionary_ParsesIntProperties()
    {
        var settings = new AppSettings();
        var dict = new Dictionary<string, string>
        {
            ["PORT"] = "3000",
            ["MAX_CONCURRENT_DOWNLOADS"] = "10",
        };

        settings.LoadFromDictionary(dict);

        Assert.Equal(3000, settings.Port);
        Assert.Equal(10, settings.MaxConcurrentDownloads);
    }

    [Fact]
    public void LoadFromDictionary_ParsesDoubleProperties()
    {
        var settings = new AppSettings();
        var dict = new Dictionary<string, string>
        {
            ["WATCH_THRESHOLD"] = "0.75",
        };

        settings.LoadFromDictionary(dict);

        Assert.Equal(0.75, settings.WatchThreshold);
    }

    [Fact]
    public void LoadFromDictionary_IgnoresUnknownKeys()
    {
        var settings = new AppSettings();
        var dict = new Dictionary<string, string>
        {
            ["UNKNOWN_KEY"] = "value",
            ["TMDB_API_KEY"] = "valid",
        };

        settings.LoadFromDictionary(dict);

        Assert.Equal("valid", settings.TmdbApiKey);
        // No exception thrown for unknown key
    }

    [Fact]
    public void LoadFromDictionary_IgnoresInvalidIntValues()
    {
        var settings = new AppSettings();
        var dict = new Dictionary<string, string>
        {
            ["PORT"] = "not_a_number",
        };

        settings.LoadFromDictionary(dict);

        // Should keep default since parse fails
        Assert.Equal(8000, settings.Port);
    }

    [Fact]
    public void LoadFromDictionary_IgnoresInvalidDoubleValues()
    {
        var settings = new AppSettings();
        var dict = new Dictionary<string, string>
        {
            ["WATCH_THRESHOLD"] = "abc",
        };

        settings.LoadFromDictionary(dict);

        Assert.Equal(0.85, settings.WatchThreshold);
    }

    [Fact]
    public void ToDictionary_ThenLoadFromDictionary_Roundtrips()
    {
        var original = new AppSettings
        {
            TmdbApiKey = "key1",
            RealDebridApiKey = "key2",
            MoviesDir = "/movies",
            TvDir = "/tv",
            AnimeDir = "/anime",
            MoviesDirArchive = "/archive/movies",
            TvDirArchive = "/archive/tv",
            AnimeDirArchive = "/archive/anime",
            DownloadsDir = "/downloads",
            PostersDir = "/posters",
            MpcBeUrl = "http://localhost:13579",
            MpcBeExe = @"C:\mpc\mpc.exe",
            Host = "127.0.0.1",
            Port = 9999,
            MaxConcurrentDownloads = 4,
            WatchThreshold = 0.7,
        };

        var dict = original.ToDictionary();
        var restored = new AppSettings();
        restored.LoadFromDictionary(dict);

        Assert.Equal(original.TmdbApiKey, restored.TmdbApiKey);
        Assert.Equal(original.RealDebridApiKey, restored.RealDebridApiKey);
        Assert.Equal(original.MoviesDir, restored.MoviesDir);
        Assert.Equal(original.TvDir, restored.TvDir);
        Assert.Equal(original.AnimeDir, restored.AnimeDir);
        Assert.Equal(original.MoviesDirArchive, restored.MoviesDirArchive);
        Assert.Equal(original.TvDirArchive, restored.TvDirArchive);
        Assert.Equal(original.AnimeDirArchive, restored.AnimeDirArchive);
        Assert.Equal(original.DownloadsDir, restored.DownloadsDir);
        Assert.Equal(original.PostersDir, restored.PostersDir);
        Assert.Equal(original.MpcBeUrl, restored.MpcBeUrl);
        Assert.Equal(original.MpcBeExe, restored.MpcBeExe);
        Assert.Equal(original.Host, restored.Host);
        Assert.Equal(original.Port, restored.Port);
        Assert.Equal(original.MaxConcurrentDownloads, restored.MaxConcurrentDownloads);
        Assert.Equal(original.WatchThreshold, restored.WatchThreshold);
    }

    [Fact]
    public void Clone_CreatesIndependentCopy()
    {
        var original = new AppSettings
        {
            TmdbApiKey = "original_key",
            Port = 5000,
        };

        var clone = original.Clone();

        Assert.Equal("original_key", clone.TmdbApiKey);
        Assert.Equal(5000, clone.Port);

        // Modifying clone should not affect original
        clone.TmdbApiKey = "modified";
        Assert.Equal("original_key", original.TmdbApiKey);
    }

    [Fact]
    public void GetEnvKey_ReturnsCorrectMapping()
    {
        Assert.Equal("TMDB_API_KEY", AppSettings.GetEnvKey("TmdbApiKey"));
        Assert.Equal("PORT", AppSettings.GetEnvKey("Port"));
        Assert.Equal("WATCH_THRESHOLD", AppSettings.GetEnvKey("WatchThreshold"));
        Assert.Equal("MPC_BE_URL", AppSettings.GetEnvKey("MpcBeUrl"));
    }

    [Fact]
    public void GetEnvKey_ReturnsInputForUnknownProperty()
    {
        Assert.Equal("UnknownProp", AppSettings.GetEnvKey("UnknownProp"));
    }

    [Fact]
    public void GetPropertyName_ReturnsCorrectReverseMapping()
    {
        Assert.Equal("TmdbApiKey", AppSettings.GetPropertyName("TMDB_API_KEY"));
        Assert.Equal("Port", AppSettings.GetPropertyName("PORT"));
        Assert.Equal("WatchThreshold", AppSettings.GetPropertyName("WATCH_THRESHOLD"));
    }

    [Fact]
    public void GetPropertyName_ReturnsInputForUnknownKey()
    {
        Assert.Equal("UNKNOWN", AppSettings.GetPropertyName("UNKNOWN"));
    }
}
