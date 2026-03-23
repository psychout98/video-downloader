using MediaDownloader.Server.Clients;

namespace MediaDownloader.Tests.Server;

public class MediaInfoTests
{
    [Fact]
    public void DisplayName_MovieWithYear()
    {
        var info = new MediaInfo { Title = "Inception", Year = 2010, Type = "movie" };
        Assert.Equal("Inception (2010)", info.DisplayName);
    }

    [Fact]
    public void DisplayName_MovieNoYear()
    {
        var info = new MediaInfo { Title = "Unknown", Type = "movie" };
        Assert.Equal("Unknown", info.DisplayName);
    }

    [Fact]
    public void DisplayName_TvWithSeasonAndEpisode()
    {
        var info = new MediaInfo { Title = "Breaking Bad", Year = 2008, Season = 1, Episode = 3 };
        Assert.Equal("Breaking Bad (2008) S01E03", info.DisplayName);
    }

    [Fact]
    public void DisplayName_TvWithSeasonOnly()
    {
        var info = new MediaInfo { Title = "Breaking Bad", Year = 2008, Season = 2 };
        Assert.Equal("Breaking Bad (2008) Season 2", info.DisplayName);
    }

    [Fact]
    public void PosterUrl_WithPath()
    {
        var info = new MediaInfo { PosterPath = "/abc123.jpg" };
        Assert.Equal("https://image.tmdb.org/t/p/w500/abc123.jpg", info.PosterUrl);
    }

    [Fact]
    public void PosterUrl_NullWhenNoPath()
    {
        var info = new MediaInfo();
        Assert.Null(info.PosterUrl);
    }

    [Fact]
    public void WithEpisode_CopiesAllFields()
    {
        var info = new MediaInfo
        {
            Title = "Show", Year = 2024, ImdbId = "tt123", TmdbId = 456,
            Type = "tv", Season = 1, Episode = null, IsAnime = true,
            PosterPath = "/poster.jpg",
            EpisodeTitles = new() { [1] = "Pilot", [2] = "Second" },
        };

        var copy = info.WithEpisode(2);

        Assert.Equal("Show", copy.Title);
        Assert.Equal(2024, copy.Year);
        Assert.Equal("tt123", copy.ImdbId);
        Assert.Equal(456, copy.TmdbId);
        Assert.Equal("tv", copy.Type);
        Assert.Equal(1, copy.Season);
        Assert.Equal(2, copy.Episode);
        Assert.True(copy.IsAnime);
        Assert.Equal("/poster.jpg", copy.PosterPath);
        Assert.Same(info.EpisodeTitles, copy.EpisodeTitles); // shallow copy
    }

    [Fact]
    public void WithEpisode_DoesNotMutateOriginal()
    {
        var info = new MediaInfo { Title = "Show", Episode = null };
        var copy = info.WithEpisode(5);

        Assert.Null(info.Episode);
        Assert.Equal(5, copy.Episode);
    }
}
