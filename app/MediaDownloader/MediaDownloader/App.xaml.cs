using System.Windows;

namespace MediaDownloader;

public partial class App : Application
{
    private static Mutex? _mutex;

    protected override void OnStartup(StartupEventArgs e)
    {
        // Single-instance enforcement (skip when MD_SKIP_MUTEX is set, e.g. in CI)
        if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("MD_SKIP_MUTEX")))
        {
            _mutex = new Mutex(true, "MediaDownloader_SingleInstance", out bool isNew);
            if (!isNew)
            {
                MessageBox.Show("Media Downloader is already running.", "Media Downloader",
                    MessageBoxButton.OK, MessageBoxImage.Information);
                Shutdown();
                return;
            }
        }

        base.OnStartup(e);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _mutex?.ReleaseMutex();
        _mutex?.Dispose();
        base.OnExit(e);
    }
}
