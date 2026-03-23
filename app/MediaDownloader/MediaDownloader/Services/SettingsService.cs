using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using MediaDownloader.Models;

namespace MediaDownloader.Services;

/// <summary>
/// Reads/writes settings from the .env file and syncs with the server API.
/// </summary>
public class SettingsService
{
    private readonly string _installDir;
    private string EnvPath => Path.Combine(_installDir, ".env");

    public SettingsService(string installDir)
    {
        _installDir = installDir;
    }

    public AppSettings Load()
    {
        var settings = new AppSettings();
        if (!File.Exists(EnvPath)) return settings;

        var dict = ParseEnvFile(EnvPath);
        settings.LoadFromDictionary(dict);
        return settings;
    }

    public async Task SaveAsync(AppSettings settings, int serverPort)
    {
        // Write to .env file
        WriteEnvFile(settings);

        // Notify the running server to reload settings
        await SyncToServerAsync(settings, serverPort);
    }

    public bool HasEnvFile() => File.Exists(EnvPath);

    private Dictionary<string, string> ParseEnvFile(string path)
    {
        var dict = new Dictionary<string, string>();
        foreach (var line in File.ReadAllLines(path))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#'))
                continue;

            var eqIndex = trimmed.IndexOf('=');
            if (eqIndex < 0) continue;

            var key = trimmed[..eqIndex].Trim();
            var value = trimmed[(eqIndex + 1)..].Trim();

            // Strip surrounding quotes
            if (value.Length >= 2 &&
                ((value.StartsWith('"') && value.EndsWith('"')) ||
                 (value.StartsWith('\'') && value.EndsWith('\''))))
            {
                value = value[1..^1];
            }

            dict[key] = value;
        }
        return dict;
    }

    private void WriteEnvFile(AppSettings settings)
    {
        var newValues = settings.ToDictionary();

        // Preserve existing keys not managed by us, and comments
        var lines = new List<string>();
        var writtenKeys = new HashSet<string>();

        if (File.Exists(EnvPath))
        {
            foreach (var line in File.ReadAllLines(EnvPath))
            {
                var trimmed = line.Trim();
                if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#'))
                {
                    lines.Add(line);
                    continue;
                }

                var eqIndex = trimmed.IndexOf('=');
                if (eqIndex < 0)
                {
                    lines.Add(line);
                    continue;
                }

                var key = trimmed[..eqIndex].Trim();
                if (newValues.TryGetValue(key, out var newVal))
                {
                    lines.Add($"{key}={newVal}");
                    writtenKeys.Add(key);
                }
                else
                {
                    lines.Add(line); // preserve unknown keys
                }
            }
        }

        // Append any new keys not in the original file
        foreach (var (key, value) in newValues)
        {
            if (!writtenKeys.Contains(key))
                lines.Add($"{key}={value}");
        }

        File.WriteAllLines(EnvPath, lines, new UTF8Encoding(false));
    }

    private async Task SyncToServerAsync(AppSettings settings, int port)
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            // Server expects {"updates": {KEY: value}} format
            var payload = new Dictionary<string, object>
            {
                ["updates"] = settings.ToDictionary()
            };
            var json = JsonSerializer.Serialize(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            await client.PostAsync($"http://127.0.0.1:{port}/api/settings", content);
        }
        catch
        {
            // Server may not be running — settings are saved to .env regardless
        }
    }
}
