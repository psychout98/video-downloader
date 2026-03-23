using System.IO;
using System.Net.Http;
using MediaDownloader.Server;
using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Services;

public enum ServerStatus
{
    Stopped,
    Starting,
    Running
}

/// <summary>
/// Manages the in-process ASP.NET Core Kestrel server lifecycle.
/// No longer spawns a Python process — the server runs directly in the WPF app.
/// </summary>
public class ServerManager : IDisposable
{
    private readonly string _installDir;
    private ServerHost? _serverHost;
    private readonly System.Timers.Timer _healthTimer;
    private readonly HttpClient _httpClient;
    private bool _disposed;

    public event Action<ServerStatus>? StatusChanged;
    public event Action<string>? OutputReceived;

    public ServerStatus Status { get; private set; } = ServerStatus.Stopped;
    public string Host { get; set; } = "0.0.0.0";
    public int Port { get; set; } = 8000;

    public ServerManager(string installDir)
    {
        _installDir = installDir;
        _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };

        _healthTimer = new System.Timers.Timer(10_000);
        _healthTimer.Elapsed += async (_, _) => await CheckHealthAsync();
        _healthTimer.AutoReset = true;
    }

    public async Task StartAsync()
    {
        if (Status == ServerStatus.Running || Status == ServerStatus.Starting)
            return;

        SetStatus(ServerStatus.Starting);

        try
        {
            var settings = ServerSettings.LoadFromEnv(_installDir);
            settings.Host = Host;
            settings.Port = Port;

            _serverHost = new ServerHost(settings);
            await _serverHost.StartAsync();

            _healthTimer.Start();

            // Wait up to 15s for health check to pass
            for (int i = 0; i < 15; i++)
            {
                await Task.Delay(1000);
                if (await IsHealthyAsync())
                {
                    SetStatus(ServerStatus.Running);
                    return;
                }
            }

            SetStatus(ServerStatus.Running); // Assume running since we started in-process
        }
        catch (Exception ex)
        {
            OutputReceived?.Invoke($"[Failed to start server: {ex.Message}]");
            SetStatus(ServerStatus.Stopped);
        }
    }

    public async Task StopAsync()
    {
        _healthTimer.Stop();

        if (_serverHost != null)
        {
            try
            {
                await _serverHost.StopAsync();
                await _serverHost.DisposeAsync();
            }
            catch { }
            _serverHost = null;
        }

        SetStatus(ServerStatus.Stopped);
    }

    public async Task RestartAsync()
    {
        await StopAsync();
        await Task.Delay(500);
        await StartAsync();
    }

    public async Task<bool> IsHealthyAsync()
    {
        try
        {
            var response = await _httpClient.GetAsync($"http://127.0.0.1:{Port}/api/status");
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    private async Task CheckHealthAsync()
    {
        var healthy = await IsHealthyAsync();
        var newStatus = healthy ? ServerStatus.Running : ServerStatus.Stopped;
        if (newStatus != Status)
            SetStatus(newStatus);
    }

    private void SetStatus(ServerStatus status)
    {
        Status = status;
        StatusChanged?.Invoke(status);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _healthTimer.Stop();
        _healthTimer.Dispose();
        _httpClient.Dispose();
        if (_serverHost != null)
        {
            _serverHost.DisposeAsync().AsTask().Wait(TimeSpan.FromSeconds(5));
            _serverHost = null;
        }
    }
}
