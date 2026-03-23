using MediaDownloader.Server.Clients;

namespace MediaDownloader.Tests.Server;

/// <summary>
/// Tests for MPC-BE variable parsing and MpcStatus properties.
/// </summary>
public class MpcClientTests
{
    [Fact]
    public void ParseVariables_Json()
    {
        var json = """{"file":"C:\\Media\\test.mkv","state":"2","position":"30000","duration":"60000","volumelevel":"80","muted":"false"}""";
        var result = MpcClient.ParseVariables(json);

        Assert.Equal("2", result["state"]);
        Assert.Equal("30000", result["position"]);
        Assert.Equal("60000", result["duration"]);
    }

    [Fact]
    public void ParseVariables_LegacyJs()
    {
        var js = """
            OnVariable("file","C:\\Media\\test.mkv");
            OnVariable("state","1");
            OnVariable("position","15000");
            OnVariable("duration","90000");
            """;
        var result = MpcClient.ParseVariables(js);

        Assert.Equal("C:\\Media\\test.mkv", result["file"]);
        Assert.Equal("1", result["state"]);
        Assert.Equal("15000", result["position"]);
    }

    [Fact]
    public void ParseVariables_Html()
    {
        var html = """
            <p id="file">C:\Media\test.mkv</p>
            <p id="filepatharg">C%3A%5CMedia%5Ctest.mkv</p>
            <p id="state">2</p>
            <p id="position">45000</p>
            <p id="duration">120000</p>
            """;
        var result = MpcClient.ParseVariables(html);

        Assert.Equal("C:\\Media\\test.mkv", result["file"]);
        Assert.Equal("C:\\Media\\test.mkv", result["filepath"]); // decoded filepatharg
        Assert.Equal("2", result["state"]);
    }

    [Fact]
    public void ParseVariables_EmptyString_ReturnsEmpty()
    {
        var result = MpcClient.ParseVariables("");
        Assert.Empty(result);
    }

    [Fact]
    public void MpcStatus_Properties_ParseCorrectly()
    {
        var data = new Dictionary<string, string>
        {
            ["file"] = @"C:\Media\Movies\Test.mkv",
            ["state"] = "2",
            ["position"] = "30000",
            ["duration"] = "60000",
            ["volumelevel"] = "80",
            ["muted"] = "false",
        };
        var status = new MpcStatus(data, reachable: true);

        Assert.True(status.Reachable);
        Assert.Equal(@"C:\Media\Movies\Test.mkv", status.File);
        Assert.Equal(2, status.State);
        Assert.True(status.IsPlaying);
        Assert.False(status.IsPaused);
        Assert.Equal(30000, status.PositionMs);
        Assert.Equal(60000, status.DurationMs);
        Assert.Equal(80, status.Volume);
        Assert.False(status.Muted);
    }

    [Fact]
    public void MpcStatus_Unreachable_HasSafeDefaults()
    {
        var status = new MpcStatus(new(), reachable: false);

        Assert.False(status.Reachable);
        Assert.Equal("", status.File);
        Assert.Equal(0, status.State);
        Assert.False(status.IsPlaying);
        Assert.Equal(0, status.PositionMs);
        Assert.Equal(0, status.DurationMs);
    }

    [Fact]
    public void MpcStatus_ToDict_ContainsAllKeys()
    {
        var status = new MpcStatus(new() { ["state"] = "0" }, reachable: true);
        var dict = status.ToDict();

        Assert.Contains("reachable", dict.Keys);
        Assert.Contains("file", dict.Keys);
        Assert.Contains("state", dict.Keys);
        Assert.Contains("is_playing", dict.Keys);
        Assert.Contains("position_ms", dict.Keys);
        Assert.Contains("duration_ms", dict.Keys);
        Assert.Contains("volume", dict.Keys);
        Assert.Contains("muted", dict.Keys);
    }

    [Fact]
    public void MpcStatus_InvalidState_DefaultsToZero()
    {
        var status = new MpcStatus(new() { ["state"] = "garbage" }, reachable: true);
        Assert.Equal(0, status.State);
    }

    [Fact]
    public void MpcStatus_Muted_ParsesVariousFormats()
    {
        Assert.True(new MpcStatus(new() { ["muted"] = "1" }, true).Muted);
        Assert.True(new MpcStatus(new() { ["muted"] = "true" }, true).Muted);
        Assert.True(new MpcStatus(new() { ["muted"] = "True" }, true).Muted);
        Assert.False(new MpcStatus(new() { ["muted"] = "0" }, true).Muted);
        Assert.False(new MpcStatus(new() { ["muted"] = "false" }, true).Muted);
    }

    [Fact]
    public void MpcStatus_PositionStr_FormatsCorrectly()
    {
        // 1h 23m 45s = 5025000ms
        var status = new MpcStatus(new() { ["position"] = "5025000", ["duration"] = "7200000" }, true);
        Assert.Equal("1:23:45", status.PositionStr);
        Assert.Equal("2:00:00", status.DurationStr);
    }

    [Fact]
    public void MpcStatus_PositionStr_NoHour()
    {
        var status = new MpcStatus(new() { ["position"] = "125000" }, true);
        Assert.Equal("2:05", status.PositionStr);
    }
}
