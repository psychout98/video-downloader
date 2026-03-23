using MediaDownloader.Server.Clients;

namespace MediaDownloader.Tests.Server;

/// <summary>
/// Tests for TmdbClient query parsing logic (no HTTP calls).
/// </summary>
public class TmdbClientTests
{
    [Fact]
    public void ParseQuery_PlainTitle()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Inception");
        Assert.Equal("Inception", query);
        Assert.Null(season);
        Assert.Null(episode);
    }

    [Fact]
    public void ParseQuery_S01E03()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Breaking Bad S01E03");
        Assert.Equal("Breaking Bad", query);
        Assert.Equal(1, season);
        Assert.Equal(3, episode);
    }

    [Fact]
    public void ParseQuery_LowercaseSE()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("show s02e10");
        Assert.Equal("show", query);
        Assert.Equal(2, season);
        Assert.Equal(10, episode);
    }

    [Fact]
    public void ParseQuery_SeasonOnly()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Breaking Bad S01");
        Assert.Equal("Breaking Bad", query);
        Assert.Equal(1, season);
        Assert.Null(episode);
    }

    [Fact]
    public void ParseQuery_SeasonWord()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Breaking Bad season 2");
        Assert.Equal("Breaking Bad", query);
        Assert.Equal(2, season);
        Assert.Null(episode);
    }

    [Fact]
    public void ParseQuery_SeasonWordCaseInsensitive()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Breaking Bad Season 3");
        Assert.Equal("Breaking Bad", query);
        Assert.Equal(3, season);
        Assert.Null(episode);
    }

    [Fact]
    public void ParseQuery_EpisodeWord()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Breaking Bad episode 5");
        Assert.Equal("Breaking Bad", query);
        Assert.Null(season);
        Assert.Equal(5, episode);
    }

    [Fact]
    public void ParseQuery_StripsTrailingYear()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Inception 2010");
        Assert.Equal("Inception", query);
        Assert.Null(season);
        Assert.Null(episode);
    }

    [Fact]
    public void ParseQuery_StripsTrailingYearInParens()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("Inception (2010)");
        Assert.Equal("Inception", query);
        Assert.Null(season);
        Assert.Null(episode);
    }

    [Fact]
    public void ParseQuery_ThreeDigitEpisode()
    {
        var (query, season, episode) = TmdbClient.ParseQuery("One Piece S01E100");
        Assert.Equal("One Piece", query);
        Assert.Equal(1, season);
        Assert.Equal(100, episode);
    }
}
