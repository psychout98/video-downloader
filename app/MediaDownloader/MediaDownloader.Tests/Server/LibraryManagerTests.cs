using MediaDownloader.Server.Core;

namespace MediaDownloader.Tests.Server;

/// <summary>
/// Tests for LibraryManager's title extraction and poster key helpers.
/// </summary>
public class LibraryManagerTests
{
    [Theory]
    [InlineData("Inception (2010)", "Inception", 2010)]
    [InlineData("The Matrix (1999)", "The Matrix", 1999)]
    [InlineData("Movie Title (2024)", "Movie Title", 2024)]
    public void ExtractTitleYear_ParenYear(string input, string expectedTitle, int expectedYear)
    {
        var (title, year) = LibraryManager.ExtractTitleYear(input);
        Assert.Equal(expectedTitle, title);
        Assert.Equal(expectedYear, year);
    }

    [Theory]
    [InlineData("Inception - 2010", "Inception", 2010)]
    public void ExtractTitleYear_DashYear(string input, string expectedTitle, int expectedYear)
    {
        var (title, year) = LibraryManager.ExtractTitleYear(input);
        Assert.Equal(expectedTitle, title);
        Assert.Equal(expectedYear, year);
    }

    [Theory]
    [InlineData("Inception.2010.1080p.BluRay", "Inception", 2010)]
    [InlineData("Movie.Title.2024.720p", "Movie Title", 2024)]
    public void ExtractTitleYear_DotYear(string input, string expectedTitle, int expectedYear)
    {
        var (title, year) = LibraryManager.ExtractTitleYear(input);
        Assert.Equal(expectedTitle, title);
        Assert.Equal(expectedYear, year);
    }

    [Theory]
    [InlineData("Breaking Bad", "Breaking Bad")]
    [InlineData("Some.Show.Name", "Some Show Name")]
    [InlineData("Show_With_Underscores", "Show With Underscores")]
    public void ExtractTitleYear_NoYear(string input, string expectedTitle)
    {
        var (title, year) = LibraryManager.ExtractTitleYear(input);
        Assert.Equal(expectedTitle, title);
        Assert.Null(year);
    }

    [Fact]
    public void ExtractTitleYear_StripsQualityTags()
    {
        var (title, year) = LibraryManager.ExtractTitleYear("Inception.2010.1080p.BluRay.x265.HEVC");
        Assert.Equal("Inception", title);
        Assert.Equal(2010, year);
    }

    [Fact]
    public void ExtractTitleYear_StripsBracketContent()
    {
        var (title, _) = LibraryManager.ExtractTitleYear("Show [1080p] (Season Pack)");
        Assert.DoesNotContain("[", title);
        Assert.DoesNotContain("(", title);
    }

    [Fact]
    public void SafePosterKey_RemovesIllegalChars()
    {
        Assert.Equal("Title _ Subtitle", LibraryManager.SafePosterKey("Title : Subtitle"));
        Assert.Equal("Movie _2024_", LibraryManager.SafePosterKey("Movie <2024>"));
        Assert.Equal("Clean", LibraryManager.SafePosterKey("Clean"));
    }
}
