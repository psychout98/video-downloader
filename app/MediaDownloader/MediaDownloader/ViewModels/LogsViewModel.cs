using System.IO;
using System.Net.Http;
using System.Windows;
using System.Windows.Input;
using MediaDownloader.Services;

namespace MediaDownloader.ViewModels;

public class LogsViewModel : ViewModelBase, IDisposable
{
    private readonly string _installDir;
    private readonly ServerManager _serverManager;
    private readonly System.Timers.Timer _pollTimer;
    private readonly HttpClient _httpClient;
    private string _logContent = "";
    private bool _autoScroll = true;
    private string _filter = "";
    private bool _disposed;

    public string LogContent { get => _logContent; set => SetField(ref _logContent, value); }
    public bool AutoScroll { get => _autoScroll; set => SetField(ref _autoScroll, value); }
    public string Filter { get => _filter; set => SetField(ref _filter, value); }

    public ICommand RefreshCommand { get; }
    public ICommand ClearCommand { get; }

    public event Action? LogsUpdated;

    private string LogFilePath => Path.Combine(_installDir, "logs", "server.log");

    public LogsViewModel(string installDir, ServerManager serverManager)
    {
        _installDir = installDir;
        _serverManager = serverManager;
        _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };

        _pollTimer = new System.Timers.Timer(5000);
        _pollTimer.Elapsed += async (_, _) => await PollLogsAsync();
        _pollTimer.AutoReset = true;

        RefreshCommand = new AsyncRelayCommand(PollLogsAsync);
        ClearCommand = new RelayCommand(() => LogContent = "");
    }

    public void StartPolling() => _pollTimer.Start();
    public void StopPolling() => _pollTimer.Stop();

    private async Task PollLogsAsync()
    {
        try
        {
            // Try the API first if server is running
            if (_serverManager.Status == ServerStatus.Running)
            {
                var response = await _httpClient.GetAsync(
                    $"http://127.0.0.1:{_serverManager.Port}/api/logs?lines=200");
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync();
                    Application.Current?.Dispatcher.Invoke(() =>
                    {
                        LogContent = content;
                        LogsUpdated?.Invoke();
                    });
                    return;
                }
            }

            // Fallback: read log file directly
            if (File.Exists(LogFilePath))
            {
                var lines = await File.ReadAllLinesAsync(LogFilePath);
                var last200 = lines.Length > 200 ? lines[^200..] : lines;
                var content = string.Join(Environment.NewLine, last200);
                Application.Current?.Dispatcher.Invoke(() =>
                {
                    LogContent = content;
                    LogsUpdated?.Invoke();
                });
            }
        }
        catch { }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _pollTimer.Stop();
        _pollTimer.Dispose();
        _httpClient.Dispose();
    }
}
