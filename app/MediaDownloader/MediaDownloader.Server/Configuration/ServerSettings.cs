namespace MediaDownloader.Server.Configuration;

/// <summary>
/// All application settings, loaded from .env file.
/// Mirrors the Python config.py Settings class.
/// </summary>
public class ServerSettings
{
    // --- Required API keys ---
    public string TmdbApiKey { get; set; } = "";
    public string RealDebridApiKey { get; set; } = "";

    // --- New unified directory settings ---
    public string MediaDir { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Media");
    public string ArchiveDir { get; set; } = @"D:\Media";

    // --- Legacy directory settings (kept for existing library layout) ---
    public string MoviesDir { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Media", "Movies");
    public string TvDir { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Media", "TV Shows");
    public string AnimeDir { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Media", "Anime");
    public string MoviesDirArchive { get; set; } = @"D:\Media\Movies";
    public string TvDirArchive { get; set; } = @"D:\Media\TV Shows";
    public string AnimeDirArchive { get; set; } = @"D:\Media\Anime";

    // Temporary download staging area
    public string DownloadsDir { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Media", "Downloads", ".staging");

    // Central poster cache
    public string PostersDir { get; set; } = "";  // Set from DataDir in LoadFromEnv

    // Per-file watch-progress (legacy JSON)
    public string ProgressFile { get; set; } = "";

    // Watch threshold (0.0 - 1.0)
    public double WatchThreshold { get; set; } = 0.85;

    // --- Server ---
    public string Host { get; set; } = "0.0.0.0";
    public int Port { get; set; } = 8000;

    // --- Download behaviour ---
    public int MaxConcurrentDownloads { get; set; } = 2;
    public int ChunkSize { get; set; } = 8 * 1024 * 1024; // 8 MB
    public int RdPollInterval { get; set; } = 30;

    // --- MPC-BE ---
    public string MpcBeUrl { get; set; } = "http://127.0.0.1:13579";
    public string MpcBeExe { get; set; } = @"C:\Program Files\MPC-BE x64\mpc-be64.exe";

    // --- Migration flag ---
    public bool Migrated { get; set; }

    // --- Derived paths ---
    public string InstallDir { get; set; } = "";
    public string DataDir => Path.Combine(InstallDir, "data");
    public string LogFile => Path.Combine(InstallDir, "logs", "server.log");
    public string EnvFile => Path.Combine(InstallDir, ".env");
    public string DbPath => Path.Combine(InstallDir, "media_downloader.db");

    private static readonly Dictionary<string, string> EnvKeyMap = new()
    {
        ["TMDB_API_KEY"] = nameof(TmdbApiKey),
        ["REAL_DEBRID_API_KEY"] = nameof(RealDebridApiKey),
        ["MEDIA_DIR"] = nameof(MediaDir),
        ["ARCHIVE_DIR"] = nameof(ArchiveDir),
        ["MOVIES_DIR"] = nameof(MoviesDir),
        ["TV_DIR"] = nameof(TvDir),
        ["ANIME_DIR"] = nameof(AnimeDir),
        ["MOVIES_DIR_ARCHIVE"] = nameof(MoviesDirArchive),
        ["TV_DIR_ARCHIVE"] = nameof(TvDirArchive),
        ["ANIME_DIR_ARCHIVE"] = nameof(AnimeDirArchive),
        ["DOWNLOADS_DIR"] = nameof(DownloadsDir),
        ["POSTERS_DIR"] = nameof(PostersDir),
        ["PROGRESS_FILE"] = nameof(ProgressFile),
        ["WATCH_THRESHOLD"] = nameof(WatchThreshold),
        ["HOST"] = nameof(Host),
        ["PORT"] = nameof(Port),
        ["MAX_CONCURRENT_DOWNLOADS"] = nameof(MaxConcurrentDownloads),
        ["CHUNK_SIZE"] = nameof(ChunkSize),
        ["RD_POLL_INTERVAL"] = nameof(RdPollInterval),
        ["MPC_BE_URL"] = nameof(MpcBeUrl),
        ["MPC_BE_EXE"] = nameof(MpcBeExe),
        ["MIGRATED"] = nameof(Migrated),
    };

    public static ServerSettings LoadFromEnv(string installDir)
    {
        var s = new ServerSettings { InstallDir = installDir };
        var envPath = Path.Combine(installDir, ".env");

        if (File.Exists(envPath))
        {
            foreach (var line in File.ReadAllLines(envPath))
            {
                var trimmed = line.Trim();
                if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#'))
                    continue;

                var eq = trimmed.IndexOf('=');
                if (eq < 0) continue;

                var key = trimmed[..eq].Trim();
                var value = trimmed[(eq + 1)..].Trim().Trim('\'', '"');

                if (!EnvKeyMap.TryGetValue(key, out var propName))
                    continue;

                var prop = typeof(ServerSettings).GetProperty(propName);
                if (prop == null) continue;

                if (prop.PropertyType == typeof(int) && int.TryParse(value, out var intVal))
                    prop.SetValue(s, intVal);
                else if (prop.PropertyType == typeof(double) && double.TryParse(value, out var dblVal))
                    prop.SetValue(s, dblVal);
                else if (prop.PropertyType == typeof(bool))
                    prop.SetValue(s, value.Equals("true", StringComparison.OrdinalIgnoreCase) || value == "1");
                else if (prop.PropertyType == typeof(string))
                    prop.SetValue(s, Environment.ExpandEnvironmentVariables(value));
            }
        }

        // Set defaults for derived paths if not overridden
        if (string.IsNullOrEmpty(s.PostersDir))
            s.PostersDir = Path.Combine(s.DataDir, "posters");
        if (string.IsNullOrEmpty(s.ProgressFile))
            s.ProgressFile = Path.Combine(s.DataDir, "playback.json");

        return s;
    }

    /// <summary>
    /// Re-read the .env file and update this instance in-place.
    /// </summary>
    public void Reload()
    {
        var fresh = LoadFromEnv(InstallDir);
        // Copy all property values from fresh to this
        foreach (var prop in typeof(ServerSettings).GetProperties())
        {
            if (prop.CanWrite && prop.Name != nameof(InstallDir))
                prop.SetValue(this, prop.GetValue(fresh));
        }
    }

    /// <summary>
    /// Get the env key name for a property name, or null.
    /// </summary>
    public static string? GetEnvKey(string propertyName)
    {
        foreach (var (envKey, propName) in EnvKeyMap)
        {
            if (propName == propertyName)
                return envKey;
        }
        return null;
    }

    /// <summary>
    /// All exposed setting keys for the settings API.
    /// </summary>
    public static readonly string[] ExposedKeys =
    [
        "TMDB_API_KEY", "REAL_DEBRID_API_KEY",
        "MEDIA_DIR", "ARCHIVE_DIR",
        "DOWNLOADS_DIR", "POSTERS_DIR",
        "MPC_BE_URL", "MPC_BE_EXE",
        "WATCH_THRESHOLD", "HOST", "PORT", "MAX_CONCURRENT_DOWNLOADS",
    ];

    public Dictionary<string, string> GetExposedValues()
    {
        var result = new Dictionary<string, string>();
        foreach (var envKey in ExposedKeys)
        {
            if (EnvKeyMap.TryGetValue(envKey, out var propName))
            {
                var prop = typeof(ServerSettings).GetProperty(propName);
                result[envKey] = prop?.GetValue(this)?.ToString() ?? "";
            }
        }
        return result;
    }
}
