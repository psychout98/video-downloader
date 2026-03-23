using MediaDownloader.Services;

namespace MediaDownloader.Tests;

public class UpdateServiceTests : IDisposable
{
    private readonly string _tempDir;
    private readonly UpdateService _service;

    public UpdateServiceTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"MediaDownloader_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);
        _service = new UpdateService(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    [Fact]
    public void CurrentVersion_ReturnsNull_WhenNoVersionFile()
    {
        Assert.Null(_service.CurrentVersion);
    }

    [Fact]
    public void CurrentVersion_ReadsFromVersionFile()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".version"), "v1.2.3\n");
        Assert.Equal("v1.2.3", _service.CurrentVersion);
    }

    [Fact]
    public void CurrentVersion_TrimsWhitespace()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".version"), "  v2.0.0  \n");
        Assert.Equal("v2.0.0", _service.CurrentVersion);
    }

    [Fact]
    public void IsNewerVersion_ReturnsTrue_WhenNoCurrentVersion()
    {
        var release = new ReleaseInfo("v1.0.0", "Release 1.0", "https://example.com/update.zip", 1024, DateTime.Now);
        Assert.True(_service.IsNewerVersion(release));
    }

    [Fact]
    public void IsNewerVersion_ReturnsFalse_WhenSameVersion()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".version"), "v1.0.0");
        var release = new ReleaseInfo("v1.0.0", "Release 1.0", "https://example.com/update.zip", 1024, DateTime.Now);
        Assert.False(_service.IsNewerVersion(release));
    }

    [Fact]
    public void IsNewerVersion_IsCaseInsensitive()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".version"), "V1.0.0");
        var release = new ReleaseInfo("v1.0.0", "Release 1.0", "https://example.com/update.zip", 1024, DateTime.Now);
        Assert.False(_service.IsNewerVersion(release));
    }

    [Fact]
    public void IsNewerVersion_ReturnsTrue_WhenDifferentVersion()
    {
        File.WriteAllText(Path.Combine(_tempDir, ".version"), "v1.0.0");
        var release = new ReleaseInfo("v2.0.0", "Release 2.0", "https://example.com/update.zip", 1024, DateTime.Now);
        Assert.True(_service.IsNewerVersion(release));
    }

    [Fact]
    public void RepoOwner_DefaultsToExpected()
    {
        Assert.Equal("psychout98", _service.RepoOwner);
    }

    [Fact]
    public void RepoName_DefaultsToExpected()
    {
        Assert.Equal("video-downloader", _service.RepoName);
    }

    [Fact]
    public void RepoOwner_CanBeChanged()
    {
        _service.RepoOwner = "other-owner";
        Assert.Equal("other-owner", _service.RepoOwner);
    }

    [Fact]
    public void ReleaseInfo_Record_HasCorrectProperties()
    {
        var published = new DateTime(2025, 1, 15);
        var release = new ReleaseInfo("v3.0.0", "Big Release", "https://dl.example.com/update.zip", 5_000_000, published);

        Assert.Equal("v3.0.0", release.TagName);
        Assert.Equal("Big Release", release.Name);
        Assert.Equal("https://dl.example.com/update.zip", release.AssetUrl);
        Assert.Equal(5_000_000, release.AssetSize);
        Assert.Equal(published, release.PublishedAt);
    }

    [Fact]
    public void ReleaseInfo_Record_SupportsEquality()
    {
        var date = DateTime.Now;
        var a = new ReleaseInfo("v1.0", "R1", "url", 100, date);
        var b = new ReleaseInfo("v1.0", "R1", "url", 100, date);
        Assert.Equal(a, b);
    }
}
