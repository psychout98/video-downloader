using MediaDownloader.Server.Api;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Core;
using MediaDownloader.Server.Data;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.FileProviders;

namespace MediaDownloader.Server;

/// <summary>
/// Bootstraps an ASP.NET Core Kestrel server in-process.
/// Replaces the Python FastAPI/uvicorn server.
/// </summary>
public class ServerHost : IAsyncDisposable
{
    private WebApplication? _app;
    private readonly ServerSettings _settings;

    public ServerHost(ServerSettings settings)
    {
        _settings = settings;
    }

    public async Task StartAsync(CancellationToken ct = default)
    {
        var builder = WebApplication.CreateSlimBuilder();

        // Configure Kestrel
        builder.WebHost.ConfigureKestrel(options =>
        {
            options.ListenAnyIP(_settings.Port);
        });

        // Logging
        builder.Logging.ClearProviders();
        builder.Logging.AddConsole();
        try
        {
            var logDir = Path.GetDirectoryName(_settings.LogFile);
            if (logDir != null) Directory.CreateDirectory(logDir);
            builder.Logging.AddProvider(new FileLoggerProvider(_settings.LogFile));
        }
        catch { /* Best effort file logging */ }

        // Register services as singletons (mirrors Python's state.py singletons)
        builder.Services.AddSingleton(_settings);
        builder.Services.AddSingleton<DbService>();
        builder.Services.AddSingleton(sp =>
            new TmdbClient(_settings.TmdbApiKey, sp.GetService<ILogger<TmdbClient>>()));
        builder.Services.AddSingleton(sp =>
            new TorrentioClient(_settings.RealDebridApiKey, sp.GetService<ILogger<TorrentioClient>>()));
        builder.Services.AddSingleton(sp =>
            new RealDebridClient(_settings.RealDebridApiKey, _settings.RdPollInterval,
                sp.GetService<ILogger<RealDebridClient>>()));
        builder.Services.AddSingleton(sp =>
            new MpcClient(_settings.MpcBeUrl, sp.GetService<ILogger<MpcClient>>()));
        builder.Services.AddSingleton(sp =>
            new LibraryManager(_settings, sp.GetService<ILogger<LibraryManager>>()));
        builder.Services.AddSingleton(sp =>
            new ProgressStore(_settings.ProgressFile, sp.GetService<ILogger<ProgressStore>>()));
        builder.Services.AddSingleton<JobProcessor>();
        builder.Services.AddHostedService(sp => sp.GetRequiredService<JobProcessor>());
        builder.Services.AddSingleton<WatchTracker>();
        builder.Services.AddHostedService(sp => sp.GetRequiredService<WatchTracker>());

        // Wire JobProcessor's client references
        builder.Services.AddSingleton(sp =>
        {
            var proc = sp.GetRequiredService<JobProcessor>();
            proc.Tmdb = sp.GetRequiredService<TmdbClient>();
            proc.Torrentio = sp.GetRequiredService<TorrentioClient>();
            proc.Rd = sp.GetRequiredService<RealDebridClient>();
            return proc;
        });

        // CORS
        builder.Services.AddCors(options =>
        {
            options.AddDefaultPolicy(policy =>
                policy.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader());
        });

        _app = builder.Build();
        _app.UseCors();

        // Initialize database
        var db = _app.Services.GetRequiredService<DbService>();
        await db.InitAsync();

        // Wire JobProcessor client references (after build)
        var processor = _app.Services.GetRequiredService<JobProcessor>();
        processor.Tmdb = _app.Services.GetRequiredService<TmdbClient>();
        processor.Torrentio = _app.Services.GetRequiredService<TorrentioClient>();
        processor.Rd = _app.Services.GetRequiredService<RealDebridClient>();

        // Map all API endpoints
        SystemEndpoints.Map(_app);
        JobsEndpoints.Map(_app);
        LibraryEndpoints.Map(_app);
        MpcEndpoints.Map(_app);
        SettingsEndpoints.Map(_app);

        // Static files + SPA fallback
        var staticDir = Path.Combine(_settings.InstallDir, "server", "static");
        if (Directory.Exists(staticDir))
        {
            var fileProvider = new PhysicalFileProvider(staticDir);
            _app.UseStaticFiles(new StaticFileOptions { FileProvider = fileProvider });

            // SPA fallback: serve index.html for non-API routes
            _app.MapFallback(async ctx =>
            {
                if (ctx.Request.Path.StartsWithSegments("/api"))
                {
                    ctx.Response.StatusCode = 404;
                    await ctx.Response.WriteAsJsonAsync(new { detail = "Not found" });
                    return;
                }

                var indexPath = Path.Combine(staticDir, "index.html");
                if (File.Exists(indexPath))
                {
                    ctx.Response.ContentType = "text/html";
                    await ctx.Response.SendFileAsync(indexPath);
                }
                else
                {
                    ctx.Response.StatusCode = 503;
                    await ctx.Response.WriteAsJsonAsync(new { detail = "Frontend not built. Run: cd frontend && npm run build" });
                }
            });
        }

        // Startup library scan (background, non-blocking)
        _ = Task.Run(async () =>
        {
            try
            {
                var library = _app.Services.GetRequiredService<LibraryManager>();
                library.Scan(force: true);
            }
            catch (Exception ex)
            {
                var logger = _app.Services.GetService<ILogger<ServerHost>>();
                logger?.LogWarning("Startup library scan failed: {Error}", ex.Message);
            }
        }, ct);

        // Ensure data directory exists
        Directory.CreateDirectory(_settings.DataDir);

        await _app.StartAsync(ct);
    }

    public async Task StopAsync(CancellationToken ct = default)
    {
        if (_app != null)
            await _app.StopAsync(ct);
    }

    public async ValueTask DisposeAsync()
    {
        if (_app != null)
        {
            await _app.DisposeAsync();
            _app = null;
        }
    }
}

/// <summary>
/// Simple file logger provider for writing to server.log.
/// </summary>
internal class FileLoggerProvider : ILoggerProvider
{
    private readonly string _path;
    private readonly object _lock = new();

    public FileLoggerProvider(string path) { _path = path; }

    public ILogger CreateLogger(string categoryName) => new FileLogger(_path, categoryName, _lock);
    public void Dispose() { }
}

internal class FileLogger : ILogger
{
    private readonly string _path;
    private readonly string _category;
    private readonly object _lock;

    public FileLogger(string path, string category, object lockObj)
    {
        _path = path;
        _category = category;
        _lock = lockObj;
    }

    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
    public bool IsEnabled(LogLevel logLevel) => logLevel >= LogLevel.Information;

    public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
    {
        if (!IsEnabled(logLevel)) return;
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} [{logLevel}] {_category}: {formatter(state, exception)}";
        if (exception != null) line += $"\n{exception}";
        lock (_lock)
        {
            try { File.AppendAllText(_path, line + "\n"); } catch { }
        }
    }
}
