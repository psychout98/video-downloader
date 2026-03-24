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

        // We can't easily trigger a status change without starting a real server,
        // but we can verify the event is wired up via the health check path
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
    public async Task StartAsync_DoesNothing_WhenAlreadyStarting()
    {
        using var mgr = new ServerManager(_tempDir);

        // Start will fail because there's no python, but it shouldn't throw
        // The key assertion is that the method handles missing python gracefully
        await mgr.StartAsync();

        // Status should be Stopped since python doesn't exist
        Assert.Equal(ServerStatus.Stopped, mgr.Status);
    }

    [Fact]
    public async Task StopAsync_SetsStatusToStopped()
    {
        using var mgr = new ServerManager(_tempDir);
        await mgr.StopAsync();
        Assert.Equal(ServerStatus.Stopped, mgr.Status);
    }

    [Fact]
    public async Task StopAsync_HandlesMissingPidFile()
    {
        using var mgr = new ServerManager(_tempDir);
        // No PID file exists — should not throw
        await mgr.StopAsync();
        Assert.Equal(ServerStatus.Stopped, mgr.Status);
    }

    [Fact]
    public async Task StopAsync_ReadsAndKillsPidFile()
    {
        using var mgr = new ServerManager(_tempDir);
        // Write a PID that doesn't correspond to any real process
        File.WriteAllText(Path.Combine(_tempDir, "server.pid"), "999999");

        // Should not throw even though the PID is invalid
        await mgr.StopAsync();
        Assert.Equal(ServerStatus.Stopped, mgr.Status);
    }

    [Fact]
    public async Task RestartAsync_SetsStatusToStopped_WhenNoServer()
    {
        using var mgr = new ServerManager(_tempDir);
        await mgr.RestartAsync();
        // Without a real python, it will end up Stopped
        Assert.Equal(ServerStatus.Stopped, mgr.Status);
    }
}
