namespace MediaDownloader.Server.Data;

public static class JobStatus
{
    public const string Pending = "pending";
    public const string Searching = "searching";
    public const string Found = "found";
    public const string AddingToRd = "adding_to_rd";
    public const string WaitingForRd = "waiting_for_rd";
    public const string Downloading = "downloading";
    public const string Organizing = "organizing";
    public const string Complete = "complete";
    public const string Failed = "failed";
    public const string Cancelled = "cancelled";

    public static readonly HashSet<string> Terminal = [Complete, Failed, Cancelled];
}
