namespace MediaDownloader.Server.Clients;

/// <summary>
/// Resolved media metadata from TMDB. Mirrors tmdb_client.MediaInfo dataclass.
/// </summary>
public class MediaInfo
{
    public string Title { get; set; } = "";
    public int? Year { get; set; }
    public string? ImdbId { get; set; }
    public int? TmdbId { get; set; }
    public string Type { get; set; } = "movie"; // "movie" | "tv" | "anime"
    public int? Season { get; set; }
    public int? Episode { get; set; }
    public string? Overview { get; set; }
    public string? PosterPath { get; set; } // e.g. "/abc123.jpg"
    public int? TotalSeasons { get; set; }
    public int? EpisodesInSeason { get; set; }
    public Dictionary<int, string> EpisodeTitles { get; set; } = new();
    public bool IsAnime { get; set; }

    public string? PosterUrl =>
        PosterPath != null ? $"https://image.tmdb.org/t/p/w500{PosterPath}" : null;

    public string DisplayName
    {
        get
        {
            var name = Year.HasValue ? $"{Title} ({Year})" : Title;
            if (Season.HasValue && Episode.HasValue)
                return $"{name} S{Season:D2}E{Episode:D2}";
            if (Season.HasValue)
                return $"{name} Season {Season}";
            return name;
        }
    }

    /// <summary>
    /// Create a shallow copy with a different episode number.
    /// </summary>
    public MediaInfo WithEpisode(int? episode)
    {
        return new MediaInfo
        {
            Title = Title, Year = Year, ImdbId = ImdbId, TmdbId = TmdbId,
            Type = Type, Season = Season, Episode = episode,
            Overview = Overview, PosterPath = PosterPath,
            TotalSeasons = TotalSeasons, EpisodesInSeason = EpisodesInSeason,
            EpisodeTitles = EpisodeTitles, IsAnime = IsAnime,
        };
    }
}
