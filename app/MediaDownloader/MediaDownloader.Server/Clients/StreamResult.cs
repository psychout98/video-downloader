namespace MediaDownloader.Server.Clients;

/// <summary>
/// A torrent/stream result from Torrentio. Mirrors torrentio_client.StreamResult.
/// </summary>
public class StreamResult
{
    public string Name { get; set; } = "";
    public string? InfoHash { get; set; }
    public string? DownloadUrl { get; set; }
    public long? SizeBytes { get; set; }
    public int Seeders { get; set; }
    public bool IsCachedRd { get; set; }
    public string? Magnet { get; set; }
    public int? FileIdx { get; set; }
}
