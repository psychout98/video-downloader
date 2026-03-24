using System.IO;
using System.Windows;
using System.Windows.Threading;

namespace MediaDownloader;

public partial class App : Application
{
    private static Mutex? _mutex;

    protected override void OnStartup(StartupEventArgs e)
    {
        // Global exception handlers to prevent silent crashes
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
        TaskScheduler.UnobservedTaskException += OnUnobservedTaskException;

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

    private void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        LogCrash("DispatcherUnhandledException", e.Exception);
        e.Handled = true; // Prevent app crash — keep the window alive
    }

    private void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        LogCrash("UnhandledException", e.ExceptionObject as Exception);
    }

    private void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        LogCrash("UnobservedTaskException", e.Exception);
        e.SetObserved(); // Prevent app crash
    }

    private static void LogCrash(string source, Exception? ex)
    {
        var msg = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {source}: {ex}";
        try
        {
            var logDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs");
            Directory.CreateDirectory(logDir);
            File.AppendAllText(Path.Combine(logDir, "crash.log"), msg + "\n");
        }
        catch { /* last resort — at least write to stderr */ }
        Console.Error.WriteLine(msg);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _mutex?.ReleaseMutex();
        _mutex?.Dispose();
        base.OnExit(e);
    }
}
