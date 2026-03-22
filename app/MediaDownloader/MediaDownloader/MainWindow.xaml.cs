using System.ComponentModel;
using System.Drawing;
using System.IO;
using System.Windows;
using MediaDownloader.Services;
using MediaDownloader.ViewModels;

namespace MediaDownloader;

public partial class MainWindow : Window
{
    private readonly MainViewModel _viewModel;
    private bool _isExiting;

    public MainWindow()
    {
        InitializeComponent();

        // Determine install directory (parent of the exe location)
        var exeDir = AppDomain.CurrentDomain.BaseDirectory;
        var installDir = exeDir; // In production, exe is in the install dir

        _viewModel = new MainViewModel(installDir);
        DataContext = _viewModel;

        DashboardTab.DataContext = _viewModel;
        SettingsTab.DataContext = _viewModel.Settings;
        LogsTab.DataContext = _viewModel.Logs;
        UpdateTab.DataContext = _viewModel.Update;

        // Set tray icon based on status
        _viewModel.PropertyChanged += OnViewModelPropertyChanged;
        UpdateTrayIcon(ServerStatus.Stopped);

        Loaded += async (_, _) => await _viewModel.InitializeAsync();
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MainViewModel.ServerStatus))
            UpdateTrayIcon(_viewModel.ServerStatus);
    }

    private void UpdateTrayIcon(ServerStatus status)
    {
        var color = status switch
        {
            ServerStatus.Running => Color.LimeGreen,
            ServerStatus.Starting => Color.Gold,
            _ => Color.IndianRed
        };

        // Create a simple colored circle icon
        using var bmp = new Bitmap(16, 16);
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        g.Clear(Color.Transparent);
        using var brush = new SolidBrush(color);
        g.FillEllipse(brush, 1, 1, 14, 14);

        var hIcon = bmp.GetHicon();
        TrayIcon.Icon = System.Drawing.Icon.FromHandle(hIcon);
        TrayIcon.ToolTipText = $"Media Downloader - {_viewModel.StatusText}";
    }

    private void Window_StateChanged(object sender, EventArgs e)
    {
        if (WindowState == WindowState.Minimized)
        {
            Hide();
            TrayIcon.ShowBalloonTip("Media Downloader", "Minimized to system tray.", Hardcodet.Wpf.TaskbarNotification.BalloonIcon.Info);
        }
    }

    private void Window_Closing(object sender, CancelEventArgs e)
    {
        if (!_isExiting)
        {
            // Minimize to tray instead of closing
            e.Cancel = true;
            WindowState = WindowState.Minimized;
            return;
        }

        _viewModel.Dispose();
        TrayIcon.Dispose();
    }

    private void TrayIcon_DoubleClick(object sender, RoutedEventArgs e) => RestoreWindow();
    private void TrayOpen_Click(object sender, RoutedEventArgs e) => RestoreWindow();

    private async void TrayStart_Click(object sender, RoutedEventArgs e)
        => await _viewModel.InitializeAsync();

    private async void TrayStop_Click(object sender, RoutedEventArgs e)
        => await _viewModel.ShutdownAsync();

    private async void TrayExit_Click(object sender, RoutedEventArgs e)
    {
        _isExiting = true;
        await _viewModel.ShutdownAsync();
        Application.Current.Shutdown();
    }

    private void RestoreWindow()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
    }
}
