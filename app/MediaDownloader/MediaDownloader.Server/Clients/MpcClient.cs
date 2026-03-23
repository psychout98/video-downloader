using System.Text.Json;
using System.Text.RegularExpressions;
using System.Web;

namespace MediaDownloader.Server.Clients;

/// <summary>
/// MPC-BE player status, parsed from /variables.html.
/// </summary>
public class MpcStatus
{
    private readonly Dictionary<string, string> _d;
    public bool Reachable { get; }

    public MpcStatus(Dictionary<string, string> data, bool reachable = true)
    {
        _d = data;
        Reachable = reachable;
    }

    public string File => _d.GetValueOrDefault("file", "") ?? _d.GetValueOrDefault("filepath", "");
    public string Filename => _d.GetValueOrDefault("filename", "") ??
        (File.Contains('\\') ? File.Split('\\')[^1] : File.Split('/')[^1]);
    public int State => int.TryParse(_d.GetValueOrDefault("state", "0"), out var v) ? v : 0;
    public bool IsPlaying => State == 2;
    public bool IsPaused => State == 1;
    public int PositionMs => int.TryParse(_d.GetValueOrDefault("position", "0"), out var v) ? v : 0;
    public int DurationMs => int.TryParse(_d.GetValueOrDefault("duration", "0"), out var v) ? v : 0;
    public string PositionStr => _d.GetValueOrDefault("positionstring", MsToStr(PositionMs));
    public string DurationStr => _d.GetValueOrDefault("durationstring", MsToStr(DurationMs));
    public int Volume => int.TryParse(_d.GetValueOrDefault("volumelevel", "100"), out var v) ? v : 100;
    public bool Muted
    {
        get
        {
            var val = _d.GetValueOrDefault("muted", "false");
            return val is "1" or "true" or "True";
        }
    }

    public Dictionary<string, object> ToDict() => new()
    {
        ["reachable"] = Reachable,
        ["file"] = File,
        ["filename"] = Filename,
        ["state"] = State,
        ["is_playing"] = IsPlaying,
        ["is_paused"] = IsPaused,
        ["position_ms"] = PositionMs,
        ["duration_ms"] = DurationMs,
        ["position_str"] = PositionStr,
        ["duration_str"] = DurationStr,
        ["volume"] = Volume,
        ["muted"] = Muted,
    };

    private static string MsToStr(int ms)
    {
        if (ms == 0) return "0:00";
        var s = ms / 1000;
        var h = s / 3600;
        var rem = s % 3600;
        var m = rem / 60;
        var sec = rem % 60;
        return h > 0 ? $"{h}:{m:D2}:{sec:D2}" : $"{m}:{sec:D2}";
    }
}

/// <summary>
/// MPC-BE web interface client. Mirrors server/clients/mpc_client.py.
/// </summary>
public class MpcClient
{
    private readonly string _baseUrl;
    private readonly ILogger? _logger;

    public MpcClient(string baseUrl, ILogger? logger = null)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _logger = logger;
    }

    public async Task<MpcStatus> GetStatusAsync(CancellationToken ct = default)
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            var response = await client.GetStringAsync($"{_baseUrl}/variables.html", ct);
            var parsed = ParseVariables(response);
            return new MpcStatus(parsed, reachable: true);
        }
        catch
        {
            return new MpcStatus(new(), reachable: false);
        }
    }

    public async Task<bool> CommandAsync(int wmCommand, Dictionary<string, string>? extra = null, CancellationToken ct = default)
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            var url = $"{_baseUrl}/command.html?wm_command={wmCommand}";
            if (extra != null)
            {
                foreach (var (k, v) in extra)
                    url += $"&{k}={Uri.EscapeDataString(v)}";
            }
            var response = await client.GetAsync(url, ct);
            return response.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    public Task<bool> PlayPauseAsync(CancellationToken ct = default) => CommandAsync(887, ct: ct);
    public Task<bool> PlayAsync(CancellationToken ct = default) => CommandAsync(891, ct: ct);
    public Task<bool> PauseAsync(CancellationToken ct = default) => CommandAsync(892, ct: ct);
    public Task<bool> StopAsync(CancellationToken ct = default) => CommandAsync(888, ct: ct);
    public Task<bool> MuteAsync(CancellationToken ct = default) => CommandAsync(909, ct: ct);
    public Task<bool> VolumeUpAsync(CancellationToken ct = default) => CommandAsync(907, ct: ct);
    public Task<bool> VolumeDownAsync(CancellationToken ct = default) => CommandAsync(908, ct: ct);
    public Task<bool> SeekAsync(int positionMs, CancellationToken ct = default) =>
        CommandAsync(889, new() { ["position"] = positionMs.ToString() }, ct);

    public async Task<bool> PingAsync(CancellationToken ct = default)
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            var response = await client.GetAsync($"{_baseUrl}/variables.html", ct);
            return response.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    public async Task<bool> OpenFileAsync(string path, CancellationToken ct = default)
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            var url = $"{_baseUrl}/command.html?wm_command=-1&path={Uri.EscapeDataString(path)}";
            var response = await client.GetAsync(url, ct);
            return response.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    internal static Dictionary<string, string> ParseVariables(string text)
    {
        var stripped = text.Trim();

        // Try JSON first (newer MPC-BE versions)
        if (stripped.StartsWith('{'))
        {
            try
            {
                var json = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(stripped);
                if (json != null)
                    return json.ToDictionary(kv => kv.Key, kv => kv.Value.ToString());
            }
            catch { /* fall through */ }
        }

        var result = new Dictionary<string, string>();

        // Legacy JS format: OnVariable("key","value");
        foreach (Match m in Regex.Matches(text, @"OnVariable\(""([^""]+)"",""([^""]*)""\)"))
            result[m.Groups[1].Value] = m.Groups[2].Value;
        if (result.Count > 0) return result;

        // HTML format: <p id="key">value</p>
        foreach (Match m in Regex.Matches(text, @"<p\s+id=""([^""]+)"">([^<]*)</p>"))
        {
            var key = m.Groups[1].Value;
            var val = m.Groups[2].Value.Trim();
            if (key == "filepatharg")
                result["filepath"] = HttpUtility.UrlDecode(val);
            result[key] = val;
        }

        return result;
    }
}
