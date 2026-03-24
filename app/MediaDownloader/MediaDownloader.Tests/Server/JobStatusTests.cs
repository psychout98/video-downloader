using MediaDownloader.Server.Data;

namespace MediaDownloader.Tests.Server;

public class JobStatusTests
{
    [Fact]
    public void Constants_MatchPythonValues()
    {
        Assert.Equal("pending", JobStatus.Pending);
        Assert.Equal("searching", JobStatus.Searching);
        Assert.Equal("found", JobStatus.Found);
        Assert.Equal("adding_to_rd", JobStatus.AddingToRd);
        Assert.Equal("waiting_for_rd", JobStatus.WaitingForRd);
        Assert.Equal("downloading", JobStatus.Downloading);
        Assert.Equal("organizing", JobStatus.Organizing);
        Assert.Equal("complete", JobStatus.Complete);
        Assert.Equal("failed", JobStatus.Failed);
        Assert.Equal("cancelled", JobStatus.Cancelled);
    }

    [Fact]
    public void Terminal_ContainsExpectedStatuses()
    {
        Assert.Contains(JobStatus.Complete, JobStatus.Terminal);
        Assert.Contains(JobStatus.Failed, JobStatus.Terminal);
        Assert.Contains(JobStatus.Cancelled, JobStatus.Terminal);
    }

    [Fact]
    public void Terminal_DoesNotContainActiveStatuses()
    {
        Assert.DoesNotContain(JobStatus.Pending, JobStatus.Terminal);
        Assert.DoesNotContain(JobStatus.Downloading, JobStatus.Terminal);
        Assert.DoesNotContain(JobStatus.WaitingForRd, JobStatus.Terminal);
    }
}
