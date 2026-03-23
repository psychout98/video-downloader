using MediaDownloader.Models;
using MediaDownloader.Services;

namespace MediaDownloader.Tests;

public class SettingsServiceTests : IDisposable
{
    private readonly string _tempDir;
    private readonly SettingsService _service;

    public SettingsServiceTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"MediaDownloader_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);
        _service = new SettingsService(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    [Fact]
    public void HasEnvFile_ReturnsFalse_WhenNoFile()
    {
        Assert.False(_service.HasEnvFile());
    }

    [Fact]
    public void HasEnvFile_ReturnsTrue_WhenFileExists()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"), "PORT=8000\n");
        Assert.True(_service.HasEnvFile());
    }

    [Fact]
    public void Load_ReturnsDefaults_WhenNoEnvFile()
    {
        var settings = _service.Load();

        Assert.Equal("", settings.TmdbApiKey);
        Assert.Equal(8000, settings.Port);
        Assert.Equal("0.0.0.0", settings.Host);
    }

    [Fact]
    public void Load_ParsesEnvFile()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "TMDB_API_KEY=abc123\n" +
            "REAL_DEBRID_API_KEY=rd789\n" +
            "PORT=9000\n" +
            "HOST=127.0.0.1\n" +
            "MEDIA_DIR=/path/to/media\n");

        var settings = _service.Load();

        Assert.Equal("abc123", settings.TmdbApiKey);
        Assert.Equal("rd789", settings.RealDebridApiKey);
        Assert.Equal(9000, settings.Port);
        Assert.Equal("127.0.0.1", settings.Host);
        Assert.Equal("/path/to/media", settings.MediaDir);
    }

    [Fact]
    public void Load_StripsQuotesFromValues()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "MEDIA_DIR=\"/path with spaces/media\"\n" +
            "ARCHIVE_DIR='/single/quoted'\n");

        var settings = _service.Load();

        Assert.Equal("/path with spaces/media", settings.MediaDir);
        Assert.Equal("/single/quoted", settings.ArchiveDir);
    }

    [Fact]
    public void Load_SkipsCommentsAndBlankLines()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "# This is a comment\n" +
            "\n" +
            "TMDB_API_KEY=valid_key\n" +
            "# Another comment\n");

        var settings = _service.Load();

        Assert.Equal("valid_key", settings.TmdbApiKey);
    }

    [Fact]
    public void Load_SkipsLinesWithoutEquals()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "INVALID_LINE\n" +
            "TMDB_API_KEY=works\n");

        var settings = _service.Load();

        Assert.Equal("works", settings.TmdbApiKey);
    }

    [Fact]
    public async Task SaveAsync_WritesEnvFile()
    {
        var settings = new AppSettings
        {
            TmdbApiKey = "save_test_key",
            Port = 3000,
            Host = "localhost",
        };

        // SaveAsync will try to sync to server (which won't exist), but should not throw
        await _service.SaveAsync(settings, 3000);

        Assert.True(File.Exists(Path.Combine(_tempDir, ".env")));
        var content = File.ReadAllText(Path.Combine(_tempDir, ".env"));
        Assert.Contains("TMDB_API_KEY=save_test_key", content);
        Assert.Contains("PORT=3000", content);
        Assert.Contains("HOST=localhost", content);
    }

    [Fact]
    public async Task SaveAsync_PreservesExistingUnmanagedKeys()
    {
        // Write an env with a custom key
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "CUSTOM_KEY=preserved_value\n" +
            "PORT=8000\n" +
            "# A comment\n");

        var settings = new AppSettings { Port = 9999 };
        await _service.SaveAsync(settings, 9999);

        var content = File.ReadAllText(Path.Combine(_tempDir, ".env"));
        Assert.Contains("CUSTOM_KEY=preserved_value", content);
        Assert.Contains("PORT=9999", content);
        Assert.Contains("# A comment", content);
    }

    [Fact]
    public async Task SaveAsync_PreservesComments()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "# Server config\n" +
            "PORT=8000\n" +
            "\n" +
            "# API Keys\n" +
            "TMDB_API_KEY=old_key\n");

        var settings = new AppSettings
        {
            TmdbApiKey = "new_key",
            Port = 8000,
        };
        await _service.SaveAsync(settings, 8000);

        var content = File.ReadAllText(Path.Combine(_tempDir, ".env"));
        Assert.Contains("# Server config", content);
        Assert.Contains("# API Keys", content);
        Assert.Contains("TMDB_API_KEY=new_key", content);
    }

    [Fact]
    public void Load_ThenSave_Roundtrips()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".env"),
            "TMDB_API_KEY=roundtrip_key\n" +
            "PORT=7777\n" +
            "WATCH_THRESHOLD=0.9\n");

        var loaded = _service.Load();

        Assert.Equal("roundtrip_key", loaded.TmdbApiKey);
        Assert.Equal(7777, loaded.Port);
        Assert.Equal(0.9, loaded.WatchThreshold);
    }
}
