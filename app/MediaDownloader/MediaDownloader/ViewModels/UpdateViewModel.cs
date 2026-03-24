using System.Windows.Input;
using MediaDownloader.Services;

namespace MediaDownloader.ViewModels;

public class UpdateViewModel : ViewModelBase
{
    private readonly UpdateService _updateService;
    private readonly ServerManager _serverManager;
    private string _currentVersion = "";
    private string _latestVersion = "";
    private string _statusMessage = "";
    private double _downloadProgress;
    private bool _isUpdateAvailable;
    private bool _isUpdating;

    public string CurrentVersion { get => _currentVersion; set => SetField(ref _currentVersion, value); }
    public string LatestVersion { get => _latestVersion; set => SetField(ref _latestVersion, value); }
    public string StatusMessage { get => _statusMessage; set => SetField(ref _statusMessage, value); }
    public double DownloadProgress { get => _downloadProgress; set => SetField(ref _downloadProgress, value); }
    public bool IsUpdateAvailable { get => _isUpdateAvailable; set => SetField(ref _isUpdateAvailable, value); }
    public bool IsUpdating { get => _isUpdating; set => SetField(ref _isUpdating, value); }

    public ICommand CheckForUpdatesCommand { get; }
    public ICommand ApplyUpdateCommand { get; }

    private ReleaseInfo? _latestRelease;

    public UpdateViewModel(UpdateService updateService, ServerManager serverManager)
    {
        _updateService = updateService;
        _serverManager = serverManager;

        CurrentVersion = updateService.CurrentVersion ?? "Unknown";

        _updateService.DownloadProgress += progress =>
        {
            System.Windows.Application.Current?.Dispatcher.Invoke(() =>
                DownloadProgress = progress * 100);
        };

        CheckForUpdatesCommand = new AsyncRelayCommand(CheckForUpdatesAsync, () => !IsUpdating);
        ApplyUpdateCommand = new AsyncRelayCommand(ApplyUpdateAsync, () => IsUpdateAvailable && !IsUpdating);
    }

    private async Task CheckForUpdatesAsync()
    {
        StatusMessage = "Checking for updates...";
        IsUpdateAvailable = false;
        _latestRelease = null;

        var release = await _updateService.CheckForUpdateAsync();
        if (release == null)
        {
            StatusMessage = "Could not check for updates. Check your internet connection.";
            return;
        }

        LatestVersion = release.TagName;

        if (_updateService.IsNewerVersion(release))
        {
            _latestRelease = release;
            IsUpdateAvailable = true;
            var sizeMb = release.AssetSize / (1024.0 * 1024.0);
            StatusMessage = $"Update available: {release.Name} ({sizeMb:F1} MB)";
        }
        else
        {
            StatusMessage = "You're up to date!";
        }
    }

    private async Task ApplyUpdateAsync()
    {
        if (_latestRelease == null) return;

        IsUpdating = true;
        DownloadProgress = 0;
        StatusMessage = "Downloading update...";

        try
        {
            await _updateService.ApplyUpdateAsync(_latestRelease, _serverManager);
            CurrentVersion = _latestRelease.TagName;
            IsUpdateAvailable = false;
            StatusMessage = "Update applied successfully! Server restarted.";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Update failed: {ex.Message}";
        }
        finally
        {
            IsUpdating = false;
        }
    }
}
