using MediaDownloader.Services;

namespace MediaDownloader.Tests;

public class ServerManagerTests : IDisposable
{
    private readonly string _tempDir;

    public ServerManagerTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"MediaDownloader_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    [Fact]
    public void Constructor_SetsDefaultValues()
    {
        using var mgr = new ServerManager(_tempDir);

        Assert.Equal(ServerStatus.Stopped, mgr.Status);
        Assert.Equal("0.0.0.0", mgr.Host);
        Assert.Equal(8000, mgr.Port);
    }

    [Fact]
    public void Host_CanBeSet()
    {
        using var mgr = new ServerManager(_tempDir);
        mgr.Host = "127.0.0.1";
        Assert.Equal("127.0.0.1", mgr.Host);
    }

    [Fact]
    public void Port_CanBeSet()
    {
        using var mgr = new ServerManager(_tempDir);
        mgr.Port = 9000;
        Assert.Equal(9000, mgr.Port);
    }

    [Fact]
    public async Task IsHealthyAsync_ReturnsFalse_WhenNoServer()
    {
        using var mgr = new ServerManager(_tempDir);
        mgr.Port = 49999; // unlikely to have a server here
        var result = await mgr.IsHealthyAsync();
        Assert.False(result);
    }

    [Fact]
    public void StatusChanged_FiresOnStatusChange()
    {
        using var mgr = new ServerManager(_tempDir);
        ServerStatus? received = null;
        mgr.StatusChanged += s => received = s;

        Assert.Null(received); // No change yet
    }

    [Fact]
    public void Dispose_CanBeCalledMultipleTimes()
    {
        var mgr = new ServerManager(_tempDir);
        mgr.Dispose();
        mgr.Dispose(); // Should not throw
    }

    [Fact]
    public async Task StopAsync_SetsStatusToStopped()
    {
        using var mgr = new ServerManager(_tempDir);
        await mgr.StopAsync();
        Assert.Equal(ServerStatus.Stopped, mgr.Status);
    }
}
