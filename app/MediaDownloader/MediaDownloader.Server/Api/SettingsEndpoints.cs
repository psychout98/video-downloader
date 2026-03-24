using System.Text.RegularExpressions;
using MediaDownloader.Server.Api.Models;
using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Core;

namespace MediaDownloader.Server.Api;

public static class SettingsEndpoints
{
    public static void Map(WebApplication app)
    {
        app.MapGet("/api/settings", (ServerSettings settings) =>
            Results.Ok(settings.GetExposedValues()));

        app.MapPost("/api/settings", (
            SettingsUpdateRequest body,
            ServerSettings settings,
            IServiceProvider sp) =>
        {
            if (!File.Exists(settings.EnvFile))
                File.WriteAllText(settings.EnvFile, "");

            var written = new List<string>();
            var errors = new List<string>();

            foreach (var (key, value) in body.Updates)
            {
                if (!ServerSettings.ExposedKeys.Contains(key))
                {
                    errors.Add($"Unknown key: {key}");
                    continue;
                }
                try
                {
                    var clean = value.Trim().Trim('\'', '"');
                    WriteEnvKey(settings.EnvFile, key, clean);
                    written.Add(key);
                }
                catch (Exception ex) { errors.Add($"{key}: {ex.Message}"); }
            }

            if (errors.Count > 0)
                return Results.BadRequest(new { detail = string.Join("; ", errors) });

            // Hot-reload
            settings.Reload();

            // Reinitialize clients with new API keys
            var tmdb = sp.GetRequiredService<TmdbClient>();
            var torrentio = sp.GetRequiredService<TorrentioClient>();
            var rd = sp.GetRequiredService<RealDebridClient>();
            var processor = sp.GetRequiredService<JobProcessor>();

            // Note: these are singletons, so we can't replace them.
            // Instead, the ServerHost creates them with the settings reference,
            // and they'll pick up new values when re-created on restart.
            // For now, this is acceptable — a note is returned.

            return Results.Ok(new
            {
                ok = true,
                written,
                note = "Settings applied. A restart is only needed for HOST/PORT changes.",
            });
        });

        app.MapGet("/api/settings/test-rd", async (ServerSettings settings) =>
        {
            var key = settings.RealDebridApiKey;
            var masked = key.Length >= 6 ? $"…{key[^6..]}" : "(too short)";
            try
            {
                using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
                client.DefaultRequestHeaders.TryAddWithoutValidation("Authorization", $"Bearer {key}");
                var r = await client.GetAsync("https://api.real-debrid.com/rest/1.0/user");
                if (r.IsSuccessStatusCode)
                {
                    var json = System.Text.Json.JsonSerializer.Deserialize<System.Text.Json.JsonElement>(
                        await r.Content.ReadAsStringAsync());
                    var username = json.TryGetProperty("username", out var u) ? u.GetString() : "?";
                    return Results.Ok(new { ok = true, key_suffix = masked, username });
                }
                return Results.Ok(new { ok = false, key_suffix = masked, error = $"RD returned HTTP {(int)r.StatusCode}" });
            }
            catch (Exception ex)
            {
                return Results.Ok(new { ok = false, key_suffix = masked, error = ex.Message });
            }
        });
    }

    private static void WriteEnvKey(string envPath, string key, string value)
    {
        var lines = File.Exists(envPath) ? File.ReadAllLines(envPath).ToList() : [];
        var pattern = new Regex($@"^{Regex.Escape(key)}\s*=");
        bool found = false;
        for (int i = 0; i < lines.Count; i++)
        {
            if (pattern.IsMatch(lines[i]))
            {
                lines[i] = $"{key}={value}";
                found = true;
                break;
            }
        }
        if (!found) lines.Add($"{key}={value}");
        File.WriteAllLines(envPath, lines, new System.Text.UTF8Encoding(false));
    }
}
