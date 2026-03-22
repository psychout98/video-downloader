namespace MediaDownloader.Models;

public class AppSettings
{
    // API Keys
    public string TmdbApiKey { get; set; } = "";
    public string RealDebridApiKey { get; set; } = "";

    // Library Directories (primary/fast storage)
    public string MoviesDir { get; set; } = "";
    public string TvDir { get; set; } = "";
    public string AnimeDir { get; set; } = "";

    // Archive Directories (secondary/slow storage)
    public string MoviesDirArchive { get; set; } = "";
    public string TvDirArchive { get; set; } = "";
    public string AnimeDirArchive { get; set; } = "";

    // Other Paths
    public string DownloadsDir { get; set; } = "";
    public string PostersDir { get; set; } = "";

    // MPC-BE
    public string MpcBeUrl { get; set; } = "http://127.0.0.1:13579";
    public string MpcBeExe { get; set; } = @"C:\Program Files\MPC-BE x64\mpc-be64.exe";

    // Server
    public string Host { get; set; } = "0.0.0.0";
    public int Port { get; set; } = 8000;
    public int MaxConcurrentDownloads { get; set; } = 2;
    public double WatchThreshold { get; set; } = 0.85;

    private static readonly Dictionary<string, string> PropertyToEnvKey = new()
    {
        ["TmdbApiKey"] = "TMDB_API_KEY",
        ["RealDebridApiKey"] = "REAL_DEBRID_API_KEY",
        ["MoviesDir"] = "MOVIES_DIR",
        ["TvDir"] = "TV_DIR",
        ["AnimeDir"] = "ANIME_DIR",
        ["MoviesDirArchive"] = "MOVIES_DIR_ARCHIVE",
        ["TvDirArchive"] = "TV_DIR_ARCHIVE",
        ["AnimeDirArchive"] = "ANIME_DIR_ARCHIVE",
        ["DownloadsDir"] = "DOWNLOADS_DIR",
        ["PostersDir"] = "POSTERS_DIR",
        ["MpcBeUrl"] = "MPC_BE_URL",
        ["MpcBeExe"] = "MPC_BE_EXE",
        ["Host"] = "HOST",
        ["Port"] = "PORT",
        ["MaxConcurrentDownloads"] = "MAX_CONCURRENT_DOWNLOADS",
        ["WatchThreshold"] = "WATCH_THRESHOLD",
    };

    public static string GetEnvKey(string propertyName)
        => PropertyToEnvKey.TryGetValue(propertyName, out var key) ? key : propertyName;

    public static string GetPropertyName(string envKey)
        => PropertyToEnvKey.FirstOrDefault(kvp => kvp.Value == envKey).Key ?? envKey;

    public Dictionary<string, string> ToDictionary()
    {
        var dict = new Dictionary<string, string>();
        foreach (var (prop, envKey) in PropertyToEnvKey)
        {
            var value = GetType().GetProperty(prop)?.GetValue(this)?.ToString() ?? "";
            dict[envKey] = value;
        }
        return dict;
    }

    public void LoadFromDictionary(Dictionary<string, string> dict)
    {
        foreach (var (envKey, value) in dict)
        {
            var propName = GetPropertyName(envKey);
            var prop = GetType().GetProperty(propName);
            if (prop == null) continue;

            if (prop.PropertyType == typeof(int) && int.TryParse(value, out var intVal))
                prop.SetValue(this, intVal);
            else if (prop.PropertyType == typeof(double) && double.TryParse(value, out var dblVal))
                prop.SetValue(this, dblVal);
            else if (prop.PropertyType == typeof(string))
                prop.SetValue(this, value);
        }
    }

    public AppSettings Clone()
    {
        var clone = new AppSettings();
        clone.LoadFromDictionary(ToDictionary());
        return clone;
    }
}
