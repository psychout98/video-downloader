using MediaDownloader.Server.Core;

namespace MediaDownloader.Tests.Server;

public class ProgressStoreTests : IDisposable
{
    private readonly string _tempDir;
    private readonly string _progressPath;

    public ProgressStoreTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"ProgressStore_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);
        _progressPath = Path.Combine(_tempDir, "progress.json");
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    [Fact]
    public void Get_ReturnsNull_WhenEmpty()
    {
        var store = new ProgressStore(_progressPath);
        Assert.Null(store.Get("nonexistent.mkv"));
    }

    [Fact]
    public void Save_ThenGet_ReturnsData()
    {
        var store = new ProgressStore(_progressPath);
        store.Save(@"C:\Media\test.mkv", 30000, 60000);

        var result = store.Get(@"C:\Media\test.mkv");
        Assert.NotNull(result);
        Assert.Equal(30000, Convert.ToInt32(result["position_ms"]));
        Assert.Equal(60000, Convert.ToInt32(result["duration_ms"]));
    }

    [Fact]
    public void Save_OverwritesPreviousEntry()
    {
        var store = new ProgressStore(_progressPath);
        store.Save("file.mkv", 10000, 60000);
        store.Save("file.mkv", 40000, 60000);

        var result = store.Get("file.mkv");
        Assert.Equal(40000, Convert.ToInt32(result!["position_ms"]));
    }

    [Fact]
    public void Pct_ReturnsCorrectFraction()
    {
        var store = new ProgressStore(_progressPath);
        store.Save("file.mkv", 30000, 60000);

        Assert.Equal(0.5, store.Pct("file.mkv"));
    }

    [Fact]
    public void Pct_ReturnsZero_WhenNotFound()
    {
        var store = new ProgressStore(_progressPath);
        Assert.Equal(0.0, store.Pct("nonexistent.mkv"));
    }

    [Fact]
    public void Pct_CapsAtOne()
    {
        var store = new ProgressStore(_progressPath);
        store.Save("file.mkv", 70000, 60000); // Over 100%

        Assert.Equal(1.0, store.Pct("file.mkv"));
    }

    [Fact]
    public void Save_PersistsToDisk()
    {
        var store = new ProgressStore(_progressPath);
        store.Save("file.mkv", 15000, 45000);

        // Load in a new instance
        var store2 = new ProgressStore(_progressPath);
        var result = store2.Get("file.mkv");
        Assert.NotNull(result);
        Assert.Equal(15000, Convert.ToInt32(result["position_ms"]));
    }

    [Fact]
    public void Constructor_HandlesCorruptFile()
    {
        File.WriteAllText(_progressPath, "not valid json{{{");
        var store = new ProgressStore(_progressPath);

        // Should not throw, should start empty
        Assert.Null(store.Get("anything"));
    }

    [Fact]
    public void Constructor_HandlesMissingFile()
    {
        var store = new ProgressStore(Path.Combine(_tempDir, "nonexistent", "progress.json"));
        Assert.Null(store.Get("anything"));
    }

    [Fact]
    public void MultipleFiles_TrackedIndependently()
    {
        var store = new ProgressStore(_progressPath);
        store.Save("a.mkv", 10000, 60000);
        store.Save("b.mkv", 50000, 60000);

        Assert.Equal(10000, Convert.ToInt32(store.Get("a.mkv")!["position_ms"]));
        Assert.Equal(50000, Convert.ToInt32(store.Get("b.mkv")!["position_ms"]));
    }
}
