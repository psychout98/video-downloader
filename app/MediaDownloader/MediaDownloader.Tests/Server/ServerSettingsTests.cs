using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Tests.Server;

public class ServerSettingsTests : IDisposable
{
    private readonly string _tempDir;

    public ServerSettingsTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"ServerSettings_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    [Fact]
    public void LoadFromEnv_WithNoFile_ReturnsDefaults()
    {
        var s = ServerSettings.LoadFromEnv(_tempDir);

        Assert.Equal("0.0.0.0", s.Host);
        Assert.Equal(8000, s.Port);
        Assert.Equal(0.85, s.WatchThreshold);
        Assert.Equal(2, s.MaxConcurrentDownloads);
        Assert.Equal("http://127.0.0.1:13579", s.MpcBeUrl);
        Assert.Equal(_tempDir, s.InstallDir);
    }

    [Fact]
    public void LoadFromEnv_ParsesAllKeyTypes()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"), """
            TMDB_API_KEY=abc123
            REAL_DEBRID_API_KEY=rd456
            PORT=9000
            MAX_CONCURRENT_DOWNLOADS=5
            WATCH_THRESHOLD=0.75
            HOST=127.0.0.1
            MIGRATED=true
            """);

        var s = ServerSettings.LoadFromEnv(_tempDir);

        Assert.Equal("abc123", s.TmdbApiKey);
        Assert.Equal("rd456", s.RealDebridApiKey);
        Assert.Equal(9000, s.Port);
        Assert.Equal(5, s.MaxConcurrentDownloads);
        Assert.Equal(0.75, s.WatchThreshold);
        Assert.Equal("127.0.0.1", s.Host);
        Assert.True(s.Migrated);
    }

    [Fact]
    public void LoadFromEnv_StripsQuotes()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"), """
            TMDB_API_KEY='quoted_key'
            REAL_DEBRID_API_KEY="double_quoted"
            """);

        var s = ServerSettings.LoadFromEnv(_tempDir);

        Assert.Equal("quoted_key", s.TmdbApiKey);
        Assert.Equal("double_quoted", s.RealDebridApiKey);
    }

    [Fact]
    public void LoadFromEnv_IgnoresCommentsAndBlankLines()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"), """
            # This is a comment

            TMDB_API_KEY=valid_key
            # Another comment
            PORT=3000
            """);

        var s = ServerSettings.LoadFromEnv(_tempDir);

        Assert.Equal("valid_key", s.TmdbApiKey);
        Assert.Equal(3000, s.Port);
    }

    [Fact]
    public void LoadFromEnv_IgnoresUnknownKeys()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"), """
            UNKNOWN_KEY=something
            TMDB_API_KEY=known
            """);

        var s = ServerSettings.LoadFromEnv(_tempDir);
        Assert.Equal("known", s.TmdbApiKey);
    }

    [Fact]
    public void LoadFromEnv_SetsDefaultPostersDir()
    {
        var s = ServerSettings.LoadFromEnv(_tempDir);

        Assert.Equal(Path.Combine(_tempDir, "data", "posters"), s.PostersDir);
    }

    [Fact]
    public void DerivedPaths_AreCorrect()
    {
        var s = ServerSettings.LoadFromEnv(_tempDir);

        Assert.Equal(Path.Combine(_tempDir, "data"), s.DataDir);
        Assert.Equal(Path.Combine(_tempDir, "logs", "server.log"), s.LogFile);
        Assert.Equal(Path.Combine(_tempDir, ".env"), s.EnvFile);
        Assert.Equal(Path.Combine(_tempDir, "media_downloader.db"), s.DbPath);
    }

    [Fact]
    public void Reload_UpdatesValues()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"), "PORT=8000");
        var s = ServerSettings.LoadFromEnv(_tempDir);
        Assert.Equal(8000, s.Port);

        File.WriteAllText(Path.Combine(_tempDir, ".env"), "PORT=9999");
        s.Reload();
        Assert.Equal(9999, s.Port);
    }

    [Fact]
    public void GetExposedValues_ReturnsExpectedKeys()
    {
        var s = ServerSettings.LoadFromEnv(_tempDir);
        var values = s.GetExposedValues();

        Assert.Contains("TMDB_API_KEY", values.Keys);
        Assert.Contains("PORT", values.Keys);
        Assert.Contains("WATCH_THRESHOLD", values.Keys);
        Assert.Contains("MPC_BE_URL", values.Keys);
    }

    [Fact]
    public void ExposedKeys_ContainsExpectedSet()
    {
        Assert.Contains("TMDB_API_KEY", ServerSettings.ExposedKeys);
        Assert.Contains("REAL_DEBRID_API_KEY", ServerSettings.ExposedKeys);
        Assert.Contains("HOST", ServerSettings.ExposedKeys);
        Assert.Contains("PORT", ServerSettings.ExposedKeys);
        Assert.DoesNotContain("MIGRATED", ServerSettings.ExposedKeys);
        Assert.DoesNotContain("CHUNK_SIZE", ServerSettings.ExposedKeys);
    }
}
