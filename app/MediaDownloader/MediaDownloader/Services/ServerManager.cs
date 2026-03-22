using System.Diagnostics;
using System.IO;
using System.Net.Http;

namespace MediaDownloader.Services;

public enum ServerStatus
{
    Stopped,
    Starting,
    Running
}

/// <summary>
/// Manages the FastAPI/uvicorn server process lifecycle.
/// </summary>
public class ServerManager : IDisposable
{
    private readonly string _installDir;
    private Process? _serverProcess;
    private readonly System.Timers.Timer _healthTimer;
    private readonly HttpClient _httpClient;
    private bool _disposed;

    public event Action<ServerStatus>? StatusChanged;

    public ServerStatus Status { get; private set; } = ServerStatus.Stopped;
    public string Host { get; set; } = "0.0.0.0";
    public int Port { get; set; } = 8000;

    private string VenvPython => Path.Combine(_installDir, ".venv", "Scripts", "python.exe");
    private string SystemPython => "python";
    private string PidFile => Path.Combine(_installDir, "server.pid");

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

        var python = File.Exists(VenvPython) ? VenvPython : SystemPython;

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = $"-m uvicorn server.main:app --host {Host} --port {Port}",
            WorkingDirectory = _installDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        try
        {
            _serverProcess = Process.Start(psi);
            if (_serverProcess != null)
            {
                // Discard output to prevent buffer deadlock
                _serverProcess.BeginOutputReadLine();
                _serverProcess.BeginErrorReadLine();
            }

            _healthTimer.Start();

            // Wait up to 30s for health check to pass
            for (int i = 0; i < 30; i++)
            {
                await Task.Delay(1000);
                if (await IsHealthyAsync())
                {
                    SetStatus(ServerStatus.Running);
                    return;
                }
                if (_serverProcess?.HasExited == true)
                {
                    SetStatus(ServerStatus.Stopped);
                    return;
                }
            }

            // Timeout — still mark as running if process alive
            if (_serverProcess?.HasExited == false)
                SetStatus(ServerStatus.Running);
            else
                SetStatus(ServerStatus.Stopped);
        }
        catch
        {
            SetStatus(ServerStatus.Stopped);
        }
    }

    public async Task StopAsync()
    {
        _healthTimer.Stop();

        // Try graceful PID-based shutdown first
        if (File.Exists(PidFile))
        {
            try
            {
                var pidStr = (await File.ReadAllTextAsync(PidFile)).Trim();
                if (int.TryParse(pidStr, out var pid))
                {
                    var proc = Process.GetProcessById(pid);
                    proc.Kill(entireProcessTree: true);
                    await proc.WaitForExitAsync();
                }
            }
            catch { }
        }

        // Also kill our tracked process
        if (_serverProcess is { HasExited: false })
        {
            try
            {
                _serverProcess.Kill(entireProcessTree: true);
                await _serverProcess.WaitForExitAsync();
            }
            catch { }
        }

        _serverProcess = null;
        SetStatus(ServerStatus.Stopped);
    }

    public async Task RestartAsync()
    {
        await StopAsync();
        await Task.Delay(1000);
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
        _serverProcess?.Dispose();
    }
}
