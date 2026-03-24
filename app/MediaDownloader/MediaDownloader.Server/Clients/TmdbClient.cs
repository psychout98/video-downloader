using System.Text.Json;
using System.Text.RegularExpressions;

namespace MediaDownloader.Server.Clients;

/// <summary>
/// TMDB API client — parses queries and resolves to structured media info.
/// Mirrors server/clients/tmdb_client.py.
/// </summary>
public class TmdbClient : BaseApiClient
{
    private const string TmdbBase = "https://api.themoviedb.org/3/";
    private readonly string _apiKey;

    private static readonly Regex AnimeKeywords = new(
        @"\b(anime|manga|ova|ona|shounen|shonen|shoujo|seinen|isekai|mecha)\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex SeFull = new(@"[Ss](\d{1,2})[Ee](\d{1,3})", RegexOptions.Compiled);
    private static readonly Regex SOnly = new(@"[Ss](\d{1,2})\b", RegexOptions.Compiled);
    private static readonly Regex SeasonWord = new(@"\bseason\s+(\d{1,2})\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex EpisodeWord = new(@"\bepisode\s+(\d{1,3})\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex ImdbUrl = new(@"imdb\.com/title/(tt\d+)", RegexOptions.Compiled);
    private static readonly Regex YearTrail = new(@"\s*\(?(19|20)\d{2}\)?$", RegexOptions.Compiled);

    public TmdbClient(string apiKey, ILogger? logger = null)
        : base(TmdbBase, timeoutSeconds: 15, maxRetries: 3, backoffBase: 1.0, logger: logger)
    {
        _apiKey = apiKey;
    }

    private async Task<JsonElement> TmdbGet(string path, Dictionary<string, string>? extraParams = null, CancellationToken ct = default)
    {
        path = path.TrimStart('/');
        var sep = path.Contains('?') ? '&' : '?';
        var url = $"{path}{sep}api_key={_apiKey}";
        if (extraParams != null)
        {
            foreach (var (k, v) in extraParams)
                url += $"&{Uri.EscapeDataString(k)}={Uri.EscapeDataString(v)}";
        }
        return await GetJsonAsync(url, ct);
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    public async Task<MediaInfo> SearchAsync(string rawQuery, CancellationToken ct = default)
    {
        var (query, season, episode) = ParseQuery(rawQuery.Trim());

        var imdbMatch = ImdbUrl.Match(rawQuery);
        if (imdbMatch.Success)
            return await LookupImdbAsync(imdbMatch.Groups[1].Value, season, episode, ct);

        if (season.HasValue || episode.HasValue)
            return await SearchTvAsync(query, season, episode, ct);

        return await SearchMultiAsync(query, season, episode, ct);
    }

    public async Task<int> GetEpisodeCountAsync(int tmdbId, int season, CancellationToken ct = default)
    {
        try
        {
            var data = await TmdbGet($"tv/{tmdbId}/season/{season}", ct: ct);
            return data.TryGetProperty("episodes", out var eps) ? eps.GetArrayLength() : 0;
        }
        catch { return 0; }
    }

    public async Task<string> GetEpisodeTitleAsync(int tmdbId, int season, int episode, CancellationToken ct = default)
    {
        try
        {
            var data = await TmdbGet($"tv/{tmdbId}/season/{season}/episode/{episode}", ct: ct);
            return data.TryGetProperty("name", out var name) ? name.GetString() ?? "" : "";
        }
        catch { return ""; }
    }

    public async Task<(string title, int? year, string? posterPath)> FuzzyResolveAsync(
        string title, string mediaType = "movie", int? year = null, CancellationToken ct = default)
    {
        bool isTv = mediaType is "tv" or "anime";
        string endpoint = isTv ? "search/tv" : "search/movie";
        string dateKey = isTv ? "first_air_date_year" : "year";
        string titleKey = isTv ? "name" : "title";

        (string, int?, string?) Extract(JsonElement best, string tkey)
        {
            var ds = GetString(best, "release_date") ?? GetString(best, "first_air_date") ?? "";
            var t = GetString(best, tkey) ?? title;
            var y = ds.Length >= 4 && int.TryParse(ds[..4], out var yy) ? yy : year;
            var pp = GetString(best, "poster_path");
            return (t, y, pp);
        }

        double Score(JsonElement item)
        {
            var t = (GetString(item, "title") ?? GetString(item, "name") ?? "").ToLowerInvariant();
            var ds = GetString(item, "release_date") ?? GetString(item, "first_air_date") ?? "";
            var iy = ds.Length >= 4 && int.TryParse(ds[..4], out var yy) ? yy : 0;
            double s = 0;
            if (t == title.ToLowerInvariant()) s += 100;
            if (t == title.ToLowerInvariant() && (!year.HasValue || iy == year)) s += 200;
            s += item.TryGetProperty("popularity", out var pop) ? pop.GetDouble() : 0;
            return s;
        }

        // Attempt 1 & 2 — type-specific, with then without year
        foreach (var withYear in new[] { true, false })
        {
            var p = new Dictionary<string, string> { ["query"] = title, ["include_adult"] = "false" };
            if (withYear && year.HasValue) p[dateKey] = year.Value.ToString();
            var data = await TmdbGet(endpoint, p, ct);
            if (data.TryGetProperty("results", out var results) && results.GetArrayLength() > 0)
            {
                var best = results.EnumerateArray().OrderByDescending(Score).First();
                return Extract(best, titleKey);
            }
        }

        // Attempt 3 — multi-search
        var multi = await TmdbGet("search/multi",
            new Dictionary<string, string> { ["query"] = title, ["include_adult"] = "false" }, ct);
        if (multi.TryGetProperty("results", out var mr))
        {
            var filtered = mr.EnumerateArray()
                .Where(x => GetString(x, "media_type") is "movie" or "tv")
                .ToList();
            if (filtered.Count > 0)
            {
                var best = filtered.OrderByDescending(Score).First();
                var tkey = GetString(best, "media_type") == "tv" ? "name" : "title";
                return Extract(best, tkey);
            }
        }

        // Attempt 4 — progressively shorten title
        var words = title.Split(' ');
        for (int drop = 1; drop < Math.Min(5, words.Length); drop++)
        {
            var shorter = string.Join(' ', words[..^drop]);
            var shortMulti = await TmdbGet("search/multi",
                new Dictionary<string, string> { ["query"] = shorter, ["include_adult"] = "false" }, ct);
            if (shortMulti.TryGetProperty("results", out var sr))
            {
                var filtered = sr.EnumerateArray()
                    .Where(x => GetString(x, "media_type") is "movie" or "tv")
                    .ToList();
                if (filtered.Count > 0)
                {
                    var best = filtered.OrderByDescending(Score).First();
                    var tkey = GetString(best, "media_type") == "tv" ? "name" : "title";
                    return Extract(best, tkey);
                }
            }
        }

        throw new InvalidOperationException($"No TMDB results for '{title}'");
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    internal static (string query, int? season, int? episode) ParseQuery(string query)
    {
        int? season = null, episode = null;

        var m = SeFull.Match(query);
        if (m.Success)
        {
            season = int.Parse(m.Groups[1].Value);
            episode = int.Parse(m.Groups[2].Value);
            return (query[..m.Index].Trim(), season, episode);
        }

        m = SeasonWord.Match(query);
        if (m.Success)
        {
            season = int.Parse(m.Groups[1].Value);
            query = query[..m.Index].Trim();
        }

        if (!season.HasValue)
        {
            m = SOnly.Match(query);
            if (m.Success)
            {
                season = int.Parse(m.Groups[1].Value);
                query = query[..m.Index].Trim();
            }
        }

        m = EpisodeWord.Match(query);
        if (m.Success)
        {
            episode = int.Parse(m.Groups[1].Value);
            query = query[..m.Index].Trim();
        }

        query = YearTrail.Replace(query, "").Trim();
        return (query, season, episode);
    }

    private async Task<MediaInfo> SearchMultiAsync(string query, int? season, int? episode, CancellationToken ct)
    {
        var data = await TmdbGet("search/multi",
            new Dictionary<string, string> { ["query"] = query, ["include_adult"] = "false" }, ct);

        if (!data.TryGetProperty("results", out var results))
            throw new InvalidOperationException($"No TMDB results for '{query}'");

        var candidates = results.EnumerateArray()
            .Where(x => GetString(x, "media_type") is "movie" or "tv")
            .OrderByDescending(x => x.TryGetProperty("popularity", out var p) ? p.GetDouble() : 0)
            .ToList();

        if (candidates.Count == 0)
            throw new InvalidOperationException($"No TMDB results for '{query}'");

        var best = candidates[0];
        return GetString(best, "media_type") == "movie"
            ? await BuildMovieInfoAsync(best, ct)
            : await BuildTvInfoAsync(best, season, episode, ct);
    }

    private async Task<MediaInfo> SearchTvAsync(string query, int? season, int? episode, CancellationToken ct)
    {
        var data = await TmdbGet("search/tv",
            new Dictionary<string, string> { ["query"] = query }, ct);

        if (!data.TryGetProperty("results", out var results) || results.GetArrayLength() == 0)
            throw new InvalidOperationException($"No TV show found for '{query}'");

        var best = results.EnumerateArray()
            .OrderByDescending(x => x.TryGetProperty("popularity", out var p) ? p.GetDouble() : 0)
            .First();

        return await BuildTvInfoAsync(best, season, episode, ct);
    }

    private async Task<MediaInfo> LookupImdbAsync(string imdbId, int? season, int? episode, CancellationToken ct)
    {
        var data = await TmdbGet($"find/{imdbId}",
            new Dictionary<string, string> { ["external_source"] = "imdb_id" }, ct);

        if (data.TryGetProperty("movie_results", out var movies) && movies.GetArrayLength() > 0)
            return await BuildMovieInfoAsync(movies[0], ct);
        if (data.TryGetProperty("tv_results", out var tvs) && tvs.GetArrayLength() > 0)
            return await BuildTvInfoAsync(tvs[0], season, episode, ct);

        throw new InvalidOperationException($"IMDb ID {imdbId} not found on TMDB");
    }

    private async Task<MediaInfo> BuildMovieInfoAsync(JsonElement tmdbResult, CancellationToken ct)
    {
        var tmdbId = tmdbResult.GetProperty("id").GetInt32();
        var ext = await TmdbGet($"movie/{tmdbId}/external_ids", ct: ct);
        var details = await TmdbGet($"movie/{tmdbId}", ct: ct);

        var title = GetString(details, "title") ?? GetString(tmdbResult, "title") ?? "Unknown";
        var yearStr = (GetString(details, "release_date") ?? "")[..Math.Min(4, (GetString(details, "release_date") ?? "").Length)];
        var year = yearStr.Length == 4 && int.TryParse(yearStr, out var y) ? y : (int?)null;

        var genres = details.TryGetProperty("genres", out var g)
            ? g.EnumerateArray().Select(x => x.GetProperty("id").GetInt32()).ToHashSet()
            : new HashSet<int>();
        var isAnime = genres.Contains(16) && GetString(details, "original_language") == "ja";

        return new MediaInfo
        {
            Title = title, Year = year,
            ImdbId = GetString(ext, "imdb_id") ?? "",
            TmdbId = tmdbId,
            Type = isAnime ? "anime" : "movie",
            IsAnime = isAnime,
            Overview = GetString(details, "overview") ?? "",
            PosterPath = GetString(details, "poster_path") ?? GetString(tmdbResult, "poster_path"),
        };
    }

    private async Task<MediaInfo> BuildTvInfoAsync(JsonElement tmdbResult, int? season, int? episode, CancellationToken ct)
    {
        var tmdbId = tmdbResult.GetProperty("id").GetInt32();
        var ext = await TmdbGet($"tv/{tmdbId}/external_ids", ct: ct);
        var details = await TmdbGet($"tv/{tmdbId}", ct: ct);

        var title = GetString(details, "name") ?? GetString(tmdbResult, "name") ?? "Unknown";
        var yearStr = (GetString(details, "first_air_date") ?? "")[..Math.Min(4, (GetString(details, "first_air_date") ?? "").Length)];
        var year = yearStr.Length == 4 && int.TryParse(yearStr, out var y) ? y : (int?)null;

        var genres = details.TryGetProperty("genres", out var g)
            ? g.EnumerateArray().Select(x => x.GetProperty("id").GetInt32()).ToHashSet()
            : new HashSet<int>();
        var origin = details.TryGetProperty("origin_country", out var oc)
            ? oc.EnumerateArray().Select(x => x.GetString() ?? "").ToHashSet()
            : new HashSet<string>();
        var isAnime = (genres.Contains(16) &&
            (GetString(details, "original_language") == "ja" || origin.Contains("JP")))
            || AnimeKeywords.IsMatch(title);

        var totalSeasons = details.TryGetProperty("number_of_seasons", out var ns) ? ns.GetInt32() : (int?)null;

        int? epCount = null;
        var epTitles = new Dictionary<int, string>();
        if (season.HasValue)
        {
            try
            {
                var sData = await TmdbGet($"tv/{tmdbId}/season/{season}", ct: ct);
                if (sData.TryGetProperty("episodes", out var eps))
                {
                    epCount = eps.GetArrayLength();
                    foreach (var ep in eps.EnumerateArray())
                    {
                        var epNum = ep.GetProperty("episode_number").GetInt32();
                        var epName = GetString(ep, "name") ?? "";
                        epTitles[epNum] = epName;
                    }
                }
            }
            catch { /* ignore */ }
        }

        return new MediaInfo
        {
            Title = title, Year = year,
            ImdbId = GetString(ext, "imdb_id") ?? "",
            TmdbId = tmdbId,
            Type = isAnime ? "anime" : "tv",
            Season = season, Episode = episode,
            TotalSeasons = totalSeasons,
            EpisodesInSeason = epCount,
            EpisodeTitles = epTitles,
            IsAnime = isAnime,
            Overview = GetString(details, "overview") ?? "",
            PosterPath = GetString(details, "poster_path") ?? GetString(tmdbResult, "poster_path"),
        };
    }

    private static string? GetString(JsonElement el, string prop)
        => el.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}
