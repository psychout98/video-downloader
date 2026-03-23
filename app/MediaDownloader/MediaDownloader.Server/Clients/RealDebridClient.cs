using System.Text.Json;

namespace MediaDownloader.Server.Clients;

public class RealDebridError : Exception
{
    public RealDebridError(string message) : base(message) { }
}

/// <summary>
/// Real-Debrid API client. Mirrors server/clients/realdebrid_client.py.
/// </summary>
public class RealDebridClient : BaseApiClient
{
    private const string RdBase = "https://api.real-debrid.com/rest/1.0";
    private static readonly HashSet<string> DoneStatuses = ["downloaded", "magnet_done"];
    private static readonly HashSet<string> ErrorStatuses = ["error", "virus", "dead", "magnet_error"];
    private const int MaxWaitSeconds = 30 * 60;

    private readonly int _pollInterval;

    public RealDebridClient(string apiKey, int pollInterval = 30, ILogger? logger = null)
        : base(timeoutSeconds: 15, maxRetries: 3, backoffBase: 2.0,
              headers: new() { ["Authorization"] = $"Bearer {apiKey}" }, logger: logger)
    {
        _pollInterval = pollInterval;
    }

    public async Task<bool> IsCachedAsync(string infoHash, CancellationToken ct = default)
    {
        try
        {
            var data = await GetJsonAsync($"{RdBase}/torrents/instantAvailability/{infoHash.ToLower()}", ct);
            if (data.TryGetProperty(infoHash.ToLower(), out var entry) &&
                entry.TryGetProperty("rd", out var rd))
                return rd.GetArrayLength() > 0;
            return false;
        }
        catch { return false; }
    }

    public async Task<string> AddMagnetAsync(string magnet, CancellationToken ct = default)
    {
        var content = new FormUrlEncodedContent(new[] { new KeyValuePair<string, string>("magnet", magnet) });
        var response = await PostAsync($"{RdBase}/torrents/addMagnet", content, ct);
        var json = await response.Content.ReadAsStringAsync(ct);
        var data = JsonSerializer.Deserialize<JsonElement>(json);
        var torrentId = data.TryGetProperty("id", out var id) ? id.GetString() : null;
        if (torrentId == null)
            throw new RealDebridError($"addMagnet returned no id: {json}");
        return torrentId;
    }

    public async Task SelectAllFilesAsync(string torrentId, CancellationToken ct = default)
    {
        var content = new FormUrlEncodedContent(new[] { new KeyValuePair<string, string>("files", "all") });
        await PostAsync($"{RdBase}/torrents/selectFiles/{torrentId}", content, ct);
    }

    public async Task<List<string>> WaitUntilDownloadedAsync(
        string torrentId, Func<int, Task>? onProgress = null,
        int maxWait = MaxWaitSeconds, CancellationToken ct = default)
    {
        var deadline = Environment.TickCount64 + maxWait * 1000L;

        while (true)
        {
            if (Environment.TickCount64 > deadline)
                throw new RealDebridError($"RD download timed out after {maxWait}s for torrent {torrentId}");

            var info = await GetTorrentInfoAsync(torrentId, ct);
            var status = info.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
            var progress = info.TryGetProperty("progress", out var p) ? p.GetInt32() : 0;

            if (onProgress != null)
                await onProgress(progress);

            if (DoneStatuses.Contains(status))
            {
                var links = info.TryGetProperty("links", out var l)
                    ? l.EnumerateArray().Select(x => x.GetString() ?? "").Where(x => x.Length > 0).ToList()
                    : new List<string>();
                if (links.Count == 0)
                    throw new RealDebridError("Torrent downloaded but no links returned");
                return links;
            }

            if (ErrorStatuses.Contains(status))
                throw new RealDebridError($"RD torrent failed with status: {status}");

            await Task.Delay(TimeSpan.FromSeconds(_pollInterval), ct);
        }
    }

    public async Task<JsonElement> GetTorrentInfoAsync(string torrentId, CancellationToken ct = default)
        => await GetJsonAsync($"{RdBase}/torrents/info/{torrentId}", ct);

    public async Task<(string url, long? size)> UnrestrictLinkAsync(string link, CancellationToken ct = default)
    {
        var content = new FormUrlEncodedContent(new[] { new KeyValuePair<string, string>("link", link) });
        var data = await PostJsonAsync($"{RdBase}/unrestrict/link", content, ct);
        var url = data.TryGetProperty("download", out var d) ? d.GetString()
                : data.TryGetProperty("url", out var u) ? u.GetString() : null;
        var size = data.TryGetProperty("filesize", out var fs) ? fs.GetInt64() : (long?)null;
        if (url == null)
            throw new RealDebridError($"unrestrict/link returned no URL");
        return (url, size);
    }

    public async Task<List<(string url, long? size)>> UnrestrictAllAsync(List<string> links, CancellationToken ct = default)
    {
        var tasks = links.Select(link => UnrestrictLinkAsync(link, ct));
        return (await Task.WhenAll(tasks)).ToList();
    }

    public async Task<(List<(string url, long? size)> files, string torrentId)> DownloadMagnetAsync(
        string magnet, Func<int, Task>? onProgress = null, CancellationToken ct = default)
    {
        var torrentId = await AddMagnetAsync(magnet, ct);
        await SelectAllFilesAsync(torrentId, ct);
        var rdLinks = await WaitUntilDownloadedAsync(torrentId, onProgress, ct: ct);
        var unrestricted = await UnrestrictAllAsync(rdLinks, ct);
        return (unrestricted, torrentId);
    }
}
