using MediaDownloader.Server.Configuration;
using MediaDownloader.Server.Data;

namespace MediaDownloader.Tests.Server;

public class DbServiceTests : IAsyncLifetime
{
    private readonly string _tempDir;
    private readonly DbService _db;

    public DbServiceTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"DbService_Test_{Guid.NewGuid()}");
        Directory.CreateDirectory(_tempDir);

        var settings = new ServerSettings { InstallDir = _tempDir };
        _db = new DbService(settings);
    }

    public async Task InitializeAsync() => await _db.InitAsync();

    public Task DisposeAsync()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
        return Task.CompletedTask;
    }

    // ------------------------------------------------------------------
    // Jobs
    // ------------------------------------------------------------------

    [Fact]
    public async Task CreateJob_ReturnsJobWithId()
    {
        var job = await _db.CreateJobAsync("test query");

        Assert.NotNull(job["id"]);
        Assert.Equal("test query", job["query"]);
        Assert.Equal("pending", job["status"]);
    }

    [Fact]
    public async Task CreateJob_WithStreamData_StoresIt()
    {
        var job = await _db.CreateJobAsync("query", "{\"test\": true}");

        Assert.Equal("{\"test\": true}", job["stream_data"]?.ToString());
    }

    [Fact]
    public async Task GetJob_ReturnsNull_WhenNotFound()
    {
        var job = await _db.GetJobAsync("nonexistent-id");
        Assert.Null(job);
    }

    [Fact]
    public async Task UpdateJob_ModifiesFields()
    {
        var job = await _db.CreateJobAsync("test");
        var id = job["id"]!.ToString()!;

        await _db.UpdateJobAsync(id, new()
        {
            ["status"] = "downloading",
            ["progress"] = 0.5,
            ["title"] = "Test Movie",
        });

        var updated = await _db.GetJobAsync(id);
        Assert.Equal("downloading", updated!["status"]);
        Assert.Equal("Test Movie", updated["title"]);
    }

    [Fact]
    public async Task AppendLog_AppendsToExistingLog()
    {
        var job = await _db.CreateJobAsync("test");
        var id = job["id"]!.ToString()!;

        await _db.AppendLogAsync(id, "Line 1");
        await _db.AppendLogAsync(id, "Line 2");

        var updated = await _db.GetJobAsync(id);
        var log = updated!["log"]?.ToString();
        Assert.Contains("Line 1", log);
        Assert.Contains("Line 2", log);
    }

    [Fact]
    public async Task GetAllJobs_ReturnsInReverseChronologicalOrder()
    {
        await _db.CreateJobAsync("first");
        await Task.Delay(10); // ensure different timestamps
        await _db.CreateJobAsync("second");

        var jobs = await _db.GetAllJobsAsync();

        Assert.Equal(2, jobs.Count);
        Assert.Equal("second", jobs[0]["query"]);
        Assert.Equal("first", jobs[1]["query"]);
    }

    [Fact]
    public async Task GetAllJobs_RespectsLimit()
    {
        for (int i = 0; i < 5; i++)
            await _db.CreateJobAsync($"job {i}");

        var jobs = await _db.GetAllJobsAsync(limit: 3);
        Assert.Equal(3, jobs.Count);
    }

    [Fact]
    public async Task GetPendingJobs_OnlyReturnsPending()
    {
        var job1 = await _db.CreateJobAsync("pending one");
        var job2 = await _db.CreateJobAsync("pending two");
        await _db.UpdateJobAsync(job2["id"]!.ToString()!, new() { ["status"] = "complete" });

        var pending = await _db.GetPendingJobsAsync();

        Assert.Single(pending);
        Assert.Equal("pending one", pending[0]["query"]);
    }

    [Fact]
    public async Task DeleteJob_RemovesJob()
    {
        var job = await _db.CreateJobAsync("to delete");
        var id = job["id"]!.ToString()!;

        var deleted = await _db.DeleteJobAsync(id);
        Assert.True(deleted);

        var result = await _db.GetJobAsync(id);
        Assert.Null(result);
    }

    [Fact]
    public async Task DeleteJob_ReturnsFalse_WhenNotFound()
    {
        var deleted = await _db.DeleteJobAsync("nonexistent");
        Assert.False(deleted);
    }

    // ------------------------------------------------------------------
    // Media Items
    // ------------------------------------------------------------------

    [Fact]
    public async Task UpsertMediaItem_InsertsNew()
    {
        await _db.UpsertMediaItemAsync(12345, "Test Movie", 2024, "movie", "Test Movie [12345]",
            overview: "A test", posterPath: "/poster.jpg", imdbId: "tt12345");

        var item = await _db.GetMediaItemAsync(12345);
        Assert.NotNull(item);
        Assert.Equal("Test Movie", item["title"]);
        Assert.Equal("movie", item["type"]);
        Assert.Equal("Test Movie [12345]", item["folder_name"]);
    }

    [Fact]
    public async Task UpsertMediaItem_UpdatesExisting()
    {
        await _db.UpsertMediaItemAsync(12345, "Old Title", 2024, "movie", "Old [12345]");
        await _db.UpsertMediaItemAsync(12345, "New Title", 2024, "movie", "New [12345]");

        var item = await _db.GetMediaItemAsync(12345);
        Assert.Equal("New Title", item!["title"]);
        Assert.Equal("New [12345]", item["folder_name"]);
    }

    // ------------------------------------------------------------------
    // Watch Progress
    // ------------------------------------------------------------------

    [Fact]
    public async Task SaveWatchProgress_StoresProgress()
    {
        await _db.UpsertMediaItemAsync(100, "Show", 2024, "tv", "Show [100]");
        await _db.SaveWatchProgressAsync(100, "S01E01.mkv", 30000, 60000);

        var progress = await _db.GetWatchProgressAsync(100, "S01E01.mkv");
        Assert.Single(progress);
        Assert.Equal(30000L, progress[0]["position_ms"]);
        Assert.Equal(60000L, progress[0]["duration_ms"]);
    }

    [Fact]
    public async Task SaveWatchProgress_MarksWatched_AboveThreshold()
    {
        await _db.UpsertMediaItemAsync(100, "Show", 2024, "tv", "Show [100]");

        var watched = await _db.SaveWatchProgressAsync(100, "S01E01.mkv", 54000, 60000, 0.85);
        Assert.True(watched); // 54000/60000 = 0.9 > 0.85
    }

    [Fact]
    public async Task SaveWatchProgress_NotWatched_BelowThreshold()
    {
        await _db.UpsertMediaItemAsync(100, "Show", 2024, "tv", "Show [100]");

        var watched = await _db.SaveWatchProgressAsync(100, "S01E01.mkv", 30000, 60000, 0.85);
        Assert.False(watched); // 30000/60000 = 0.5 < 0.85
    }

    [Fact]
    public async Task GetContinueWatching_ReturnsPartiallyWatched()
    {
        await _db.UpsertMediaItemAsync(100, "Show", 2024, "tv", "Show [100]");
        await _db.SaveWatchProgressAsync(100, "S01E01.mkv", 30000, 60000); // partial
        await _db.SaveWatchProgressAsync(100, "S01E02.mkv", 58000, 60000); // watched (96%)

        var continuing = await _db.GetContinueWatchingAsync();

        // Only the partial one (S01E01) should appear
        Assert.Single(continuing);
        Assert.Equal("S01E01.mkv", continuing[0]["rel_path"]);
    }

    [Fact]
    public async Task InitAsync_IsIdempotent()
    {
        // Should not throw when called multiple times
        await _db.InitAsync();
        await _db.InitAsync();

        // DB should still work
        var job = await _db.CreateJobAsync("after re-init");
        Assert.NotNull(job);
    }
}
