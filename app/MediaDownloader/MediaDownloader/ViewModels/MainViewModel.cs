using System.Diagnostics;
using System.Windows;
using System.Windows.Input;
using MediaDownloader.Services;

namespace MediaDownloader.ViewModels;

public class MainViewModel : ViewModelBase, IDisposable
{
    private readonly ServerManager _serverManager;
    private readonly SettingsService _settingsService;
    private readonly UpdateService _updateService;
    private readonly string _installDir;

    private ServerStatus _serverStatus = ServerStatus.Stopped;
    private string _statusText = "Stopped";

    public ServerStatus ServerStatus
    {
        get => _serverStatus;
        private set
        {
            if (SetField(ref _serverStatus, value))
            {
                StatusText = value switch
                {
                    ServerStatus.Running => "Running",
                    ServerStatus.Starting => "Starting...",
                    _ => "Stopped"
                };
                OnPropertyChanged(nameof(StatusColor));
                OnPropertyChanged(nameof(CanStart));
                OnPropertyChanged(nameof(CanStop));
            }
        }
    }

    public string StatusText { get => _statusText; set => SetField(ref _statusText, value); }

    public string StatusColor => ServerStatus switch
    {
        ServerStatus.Running => "#4ade80",
        ServerStatus.Starting => "#fbbf24",
        _ => "#f87171"
    };

    public bool CanStart => ServerStatus == ServerStatus.Stopped;
    public bool CanStop => ServerStatus == ServerStatus.Running;

    public ICommand StartCommand { get; }
    public ICommand StopCommand { get; }
    public ICommand RestartCommand { get; }
    public ICommand OpenWebUiCommand { get; }

    public SettingsViewModel Settings { get; }
    public LogsViewModel Logs { get; }
    public UpdateViewModel Update { get; }

    public MainViewModel(string installDir)
    {
        _installDir = installDir;
        _settingsService = new SettingsService(installDir);
        _serverManager = new ServerManager(installDir);
        _updateService = new UpdateService(installDir);

        // Load settings to get port
        var appSettings = _settingsService.Load();
        _serverManager.Port = appSettings.Port;
        _serverManager.Host = appSettings.Host;

        _serverManager.StatusChanged += status =>
        {
            Application.Current?.Dispatcher.Invoke(() => ServerStatus = status);
        };

        Settings = new SettingsViewModel(_settingsService, _serverManager);
        Logs = new LogsViewModel(installDir, _serverManager);
        Update = new UpdateViewModel(_updateService, _serverManager);

        StartCommand = new AsyncRelayCommand(
            () => _serverManager.StartAsync(),
            () => CanStart);
        StopCommand = new AsyncRelayCommand(
            () => _serverManager.StopAsync(),
            () => CanStop);
        RestartCommand = new AsyncRelayCommand(
            () => _serverManager.RestartAsync(),
            () => CanStop);
        OpenWebUiCommand = new RelayCommand(() =>
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = $"http://localhost:{_serverManager.Port}",
                UseShellExecute = true
            });
        });
    }

    public async Task InitializeAsync()
    {
        // Auto-start server on launch
        await _serverManager.StartAsync();
        Logs.StartPolling();
    }

    public async Task ShutdownAsync()
    {
        Logs.StopPolling();
        await _serverManager.StopAsync();
    }

    public void Dispose()
    {
        _serverManager.Dispose();
        Logs.Dispose();
    }
}
