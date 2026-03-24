namespace MediaDownloader.Server.Api.Models;

public record SearchRequest(string Query);
public record DownloadRequest(string SearchId, int StreamIndex);
public record MpcCommandRequest(int Command, int? PositionMs = null);
public record MpcOpenRequest(int TmdbId, string RelPath, List<string>? Playlist = null);
public record SettingsUpdateRequest(Dictionary<string, string> Updates);
public record ProgressUpdateRequest(string Path, int PositionMs, int DurationMs);
