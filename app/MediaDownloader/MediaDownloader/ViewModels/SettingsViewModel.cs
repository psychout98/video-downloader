using System.Net.Http;
using System.Text.Json;
using System.Windows.Input;
using MediaDownloader.Models;
using MediaDownloader.Services;

namespace MediaDownloader.ViewModels;

public class SettingsViewModel : ViewModelBase
{
    private readonly SettingsService _settingsService;
    private readonly ServerManager _serverManager;
    private AppSettings _original = new();
    private bool _isDirty;
    private string _rdTestResult = "";
    private bool _startOnBoot;

    // API Keys
    private string _tmdbApiKey = "";
    private string _realDebridApiKey = "";

    // Unified directories
    private string _mediaDir = "";
    private string _archiveDir = "";

    // Other Paths
    private string _downloadsDir = "";
    private string _postersDir = "";

    // MPC-BE
    private string _mpcBeUrl = "";
    private string _mpcBeExe = "";

    // Server
    private string _host = "";
    private string _port = "";
    private string _maxConcurrentDownloads = "";
    private string _watchThreshold = "";

    public string TmdbApiKey { get => _tmdbApiKey; set { if (SetField(ref _tmdbApiKey, value)) MarkDirty(); } }
    public string RealDebridApiKey { get => _realDebridApiKey; set { if (SetField(ref _realDebridApiKey, value)) MarkDirty(); } }
    public string MediaDir { get => _mediaDir; set { if (SetField(ref _mediaDir, value)) MarkDirty(); } }
    public string ArchiveDir { get => _archiveDir; set { if (SetField(ref _archiveDir, value)) MarkDirty(); } }
    public string DownloadsDir { get => _downloadsDir; set { if (SetField(ref _downloadsDir, value)) MarkDirty(); } }
    public string PostersDir { get => _postersDir; set { if (SetField(ref _postersDir, value)) MarkDirty(); } }
    public string MpcBeUrl { get => _mpcBeUrl; set { if (SetField(ref _mpcBeUrl, value)) MarkDirty(); } }
    public string MpcBeExe { get => _mpcBeExe; set { if (SetField(ref _mpcBeExe, value)) MarkDirty(); } }
    public string Host { get => _host; set { if (SetField(ref _host, value)) MarkDirty(); } }
    public string Port { get => _port; set { if (SetField(ref _port, value)) MarkDirty(); } }
    public string MaxConcurrentDownloads { get => _maxConcurrentDownloads; set { if (SetField(ref _maxConcurrentDownloads, value)) MarkDirty(); } }
    public string WatchThreshold { get => _watchThreshold; set { if (SetField(ref _watchThreshold, value)) MarkDirty(); } }

    public bool IsDirty { get => _isDirty; private set => SetField(ref _isDirty, value); }
    public string RdTestResult { get => _rdTestResult; set => SetField(ref _rdTestResult, value); }
    public bool StartOnBoot
    {
        get => _startOnBoot;
        set
        {
            if (SetField(ref _startOnBoot, value))
            {
                var exePath = System.Diagnostics.Process.GetCurrentProcess().MainModule?.FileName ?? "";
                StartupManager.SetEnabled(value, exePath);
            }
        }
    }

    public ICommand SaveCommand { get; }
    public ICommand DiscardCommand { get; }
    public ICommand TestRdKeyCommand { get; }

    public SettingsViewModel(SettingsService settingsService, ServerManager serverManager)
    {
        _settingsService = settingsService;
        _serverManager = serverManager;

        SaveCommand = new AsyncRelayCommand(SaveAsync, () => IsDirty);
        DiscardCommand = new RelayCommand(LoadFromDisk, () => IsDirty);
        TestRdKeyCommand = new AsyncRelayCommand(TestRdKeyAsync);

        LoadFromDisk();
        _startOnBoot = StartupManager.IsEnabled();
    }

    private void LoadFromDisk()
    {
        _original = _settingsService.Load();
        ApplyFromModel(_original);
        IsDirty = false;
    }

    private void ApplyFromModel(AppSettings s)
    {
        // Suppress dirty tracking during load
        _tmdbApiKey = s.TmdbApiKey; OnPropertyChanged(nameof(TmdbApiKey));
        _realDebridApiKey = s.RealDebridApiKey; OnPropertyChanged(nameof(RealDebridApiKey));
        _mediaDir = s.MediaDir; OnPropertyChanged(nameof(MediaDir));
        _archiveDir = s.ArchiveDir; OnPropertyChanged(nameof(ArchiveDir));
        _downloadsDir = s.DownloadsDir; OnPropertyChanged(nameof(DownloadsDir));
        _postersDir = s.PostersDir; OnPropertyChanged(nameof(PostersDir));
        _mpcBeUrl = s.MpcBeUrl; OnPropertyChanged(nameof(MpcBeUrl));
        _mpcBeExe = s.MpcBeExe; OnPropertyChanged(nameof(MpcBeExe));
        _host = s.Host; OnPropertyChanged(nameof(Host));
        _port = s.Port.ToString(); OnPropertyChanged(nameof(Port));
        _maxConcurrentDownloads = s.MaxConcurrentDownloads.ToString(); OnPropertyChanged(nameof(MaxConcurrentDownloads));
        _watchThreshold = s.WatchThreshold.ToString(); OnPropertyChanged(nameof(WatchThreshold));
    }

    private AppSettings BuildModel()
    {
        return new AppSettings
        {
            TmdbApiKey = TmdbApiKey,
            RealDebridApiKey = RealDebridApiKey,
            MediaDir = MediaDir,
            ArchiveDir = ArchiveDir,
            DownloadsDir = DownloadsDir,
            PostersDir = PostersDir,
            MpcBeUrl = MpcBeUrl,
            MpcBeExe = MpcBeExe,
            Host = Host,
            Port = int.TryParse(Port, out var p) ? p : 8000,
            MaxConcurrentDownloads = int.TryParse(MaxConcurrentDownloads, out var m) ? m : 2,
            WatchThreshold = double.TryParse(WatchThreshold, out var w) ? w : 0.85,
        };
    }

    private async Task SaveAsync()
    {
        var model = BuildModel();
        await _settingsService.SaveAsync(model, _serverManager.Port);
        _original = model;
        IsDirty = false;
    }

    private async Task TestRdKeyAsync()
    {
        RdTestResult = "Testing...";
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
            client.DefaultRequestHeaders.Add("Authorization", $"Bearer {RealDebridApiKey}");
            var response = await client.GetAsync("https://api.real-debrid.com/rest/1.0/user");

            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                var username = doc.RootElement.GetProperty("username").GetString();
                RdTestResult = $"Valid - {username}";
            }
            else
            {
                RdTestResult = $"Invalid (HTTP {(int)response.StatusCode})";
            }
        }
        catch (Exception ex)
        {
            RdTestResult = $"Error: {ex.Message}";
        }
    }

    private void MarkDirty() => IsDirty = true;
}
