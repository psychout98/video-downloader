using System.Text.Json;
using System.Text.RegularExpressions;

namespace MediaDownloader.Server.Clients;

/// <summary>
/// Torrentio Stremio addon client. Mirrors server/clients/torrentio_client.py.
/// </summary>
public class TorrentioClient : BaseApiClient
{
    private const string TorrentioBase = "https://torrentio.strem.fun";
    private static readonly Regex SeedersRe = new(@"👤\s*(\d+)", RegexOptions.Compiled);
    private static readonly Regex SizeRe = new(@"💾\s*([\d.]+)\s*(GB|MB|TB)", RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private readonly string _rdKey;

    public TorrentioClient(string rdApiKey, ILogger? logger = null)
        : base(timeoutSeconds: 20, maxRetries: 3, backoffBase: 2.0,
              headers: new()
              {
                  ["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                  ["Accept"] = "application/json, */*",
              }, logger: logger)
    {
        _rdKey = rdApiKey;
    }

    private string BuildUrl(MediaInfo media, bool cachedOnly)
    {
        var options = cachedOnly && !string.IsNullOrEmpty(_rdKey)
            ? $"realdebrid={_rdKey}|sort=qualitysize|limit=20"
            : "sort=qualitysize|limit=20";

        string streamType, streamId;
        if (media.Type is "tv" or "anime" && media.Season.HasValue)
        {
            var ep = media.Episode ?? 1;
            streamId = $"{media.ImdbId}:{media.Season}:{ep}";
            streamType = "series";
        }
        else
        {
            streamId = media.ImdbId!;
            streamType = "movie";
        }

        return $"{TorrentioBase}/{options}/stream/{streamType}/{streamId}.json";
    }

    public async Task<List<StreamResult>> GetStreamsAsync(
        MediaInfo media, bool cachedOnly = true, CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(media.ImdbId))
            return [];

        var url = BuildUrl(media, cachedOnly);

        JsonElement data;
        try
        {
            data = await GetJsonAsync(url, ct);
        }
        catch { return []; }

        if (!data.TryGetProperty("streams", out var streams))
            return [];

        var results = new List<StreamResult>();
        foreach (var s in streams.EnumerateArray())
        {
            var name = s.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
            var title = s.TryGetProperty("title", out var t) ? t.GetString() ?? "" : "";
            var infoHash = s.TryGetProperty("infoHash", out var ih) ? ih.GetString() : null;
            if (infoHash == null && s.TryGetProperty("infoHashes", out var ihs) && ihs.GetArrayLength() > 0)
                infoHash = ihs[0].GetString();
            var downloadUrl = s.TryGetProperty("url", out var u) ? u.GetString() : null;
            var fileIdx = s.TryGetProperty("fileIdx", out var fi) ? fi.GetInt32() : (int?)null;

            // Build magnet if we have a hash but no URL
            string? magnet = null;
            if (infoHash != null && downloadUrl == null)
            {
                var trackers = "";
                if (s.TryGetProperty("sources", out var sources))
                {
                    var trList = sources.EnumerateArray()
                        .Select(x => x.GetString() ?? "")
                        .Where(x => x.StartsWith("tracker:"))
                        .Select(x => $"tr={x.Replace("tracker:", "")}");
                    trackers = string.Join("&", trList);
                }
                magnet = !string.IsNullOrEmpty(trackers)
                    ? $"magnet:?xt=urn:btih:{infoHash}&{trackers}"
                    : $"magnet:?xt=urn:btih:{infoHash}";
            }

            var combined = $"{name} {title}";
            results.Add(new StreamResult
            {
                Name = combined,
                InfoHash = infoHash,
                DownloadUrl = downloadUrl,
                SizeBytes = ParseSize(title),
                Seeders = ParseSeeders(title),
                IsCachedRd = downloadUrl != null,
                Magnet = magnet,
                FileIdx = fileIdx,
            });
        }

        results.Sort((a, b) =>
        {
            var c = b.IsCachedRd.CompareTo(a.IsCachedRd);
            return c != 0 ? c : (b.SizeBytes ?? 0).CompareTo(a.SizeBytes ?? 0);
        });

        return results;
    }

    private static long? ParseSize(string text)
    {
        var m = SizeRe.Match(text);
        if (!m.Success) return null;
        var val = double.Parse(m.Groups[1].Value);
        var unit = m.Groups[2].Value.ToUpperInvariant();
        var multiplier = unit switch
        {
            "MB" => 1024L * 1024,
            "GB" => 1024L * 1024 * 1024,
            "TB" => 1024L * 1024 * 1024 * 1024,
            _ => 1L,
        };
        return (long)(val * multiplier);
    }

    private static int ParseSeeders(string text)
    {
        var m = SeedersRe.Match(text);
        return m.Success ? int.Parse(m.Groups[1].Value) : 0;
    }
}
