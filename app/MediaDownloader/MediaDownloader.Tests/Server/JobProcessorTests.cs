using MediaDownloader.Server.Core;

namespace MediaDownloader.Tests.Server;

/// <summary>
/// Tests for JobProcessor's episode parsing and filename helpers.
/// </summary>
public class JobProcessorTests
{
    [Theory]
    [InlineData("Show S01E03 - Title.mkv", 3)]
    [InlineData("Show.s02e15.720p.mkv", 15)]
    [InlineData("Show S1E100.mkv", 100)]
    public void EpisodeFromFilename_StandardSxEx(string filename, int expected)
    {
        Assert.Equal(expected, JobProcessor.EpisodeFromFilename(filename));
    }

    [Theory]
    [InlineData("Show E03.mkv", 3)]
    [InlineData("Show.Ep12.mkv", 12)]
    [InlineData("E05 - Title.mkv", 5)]
    public void EpisodeFromFilename_EpPattern(string filename, int expected)
    {
        Assert.Equal(expected, JobProcessor.EpisodeFromFilename(filename));
    }

    [Theory]
    [InlineData("Show - 03 - Episode Title.mkv", 3)]
    [InlineData("[SubGroup] Show - 12 - Title.mkv", 12)]
    public void EpisodeFromFilename_AnimeDashPattern(string filename, int expected)
    {
        Assert.Equal(expected, JobProcessor.EpisodeFromFilename(filename));
    }

    [Theory]
    [InlineData("[SubGroup] Show - 07.mkv", 7)]
    [InlineData("Show - 24 [720p].mkv", 24)]
    public void EpisodeFromFilename_AnimeDashEndPattern(string filename, int expected)
    {
        Assert.Equal(expected, JobProcessor.EpisodeFromFilename(filename));
    }

    [Theory]
    [InlineData("Movie.2024.1080p.mkv")]
    [InlineData("random_file.mkv")]
    [InlineData("")]
    public void EpisodeFromFilename_ReturnsNull_WhenNoMatch(string filename)
    {
        Assert.Null(JobProcessor.EpisodeFromFilename(filename));
    }
}
