using MediaDownloader.Server.Clients;
using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Server.Core;

/// <summary>
/// Monitors MPC-BE and archives watched files.
/// Mirrors server/core/watch_tracker.py.
/// </summary>
public class WatchTracker : BackgroundService
{
    private static readonly HashSet<string> VideoExts = [".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"];
    private static readonly HashSet<string> SubtitleExts = [".srt", ".ass", ".sub", ".idx", ".vtt", ".nfo"];
    private const int PollInterval = 5;
    private const int ProgressSaveInterval = 10;

    private readonly MpcClient _mpc;
    private readonly ProgressStore? _progress;
    private readonly ServerSettings _settings;
    private readonly ILogger<WatchTracker> _logger;

    private readonly (string primary, string archive)[] _dirPairs;
    private string? _prevFile;
    private readonly Dictionary<string, double> _maxPct = new();
    private int _stoppedPolls;
    private double _lastProgressSave;

    public WatchTracker(MpcClient mpc, ProgressStore? progressStore, ServerSettings settings, ILogger<WatchTracker> logger)
    {
        _mpc = mpc;
        _progress = progressStore;
        _settings = settings;
        _logger = logger;
        _dirPairs =
        [
            (settings.MoviesDir, settings.MoviesDirArchive),
            (settings.TvDir, settings.TvDirArchive),
            (settings.AnimeDir, settings.AnimeDirArchive),
        ];
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        _logger.LogInformation("WatchTracker started (threshold={Threshold:P0})", _settings.WatchThreshold);

        while (!ct.IsCancellationRequested)
        {
            try { await TickAsync(ct); }
            catch (Exception ex) { _logger.LogDebug("WatchTracker tick error: {Error}", ex.Message); }
            await Task.Delay(TimeSpan.FromSeconds(PollInterval), ct);
        }
    }

    private async Task TickAsync(CancellationToken ct)
    {
        MpcStatus status;
        try { status = await _mpc.GetStatusAsync(ct); }
        catch
        {
            if (_prevFile != null)
            {
                _stoppedPolls++;
                if (_stoppedPolls >= 2) await OnStoppedAsync(_prevFile);
            }
            return;
        }

        if (status.State is 1 or 2 && !string.IsNullOrEmpty(status.File))
        {
            _stoppedPolls = 0;
            if (status.DurationMs > 0)
            {
                var pct = (double)status.PositionMs / status.DurationMs;
                _maxPct[status.File] = Math.Max(_maxPct.GetValueOrDefault(status.File, 0.0), pct);

                var now = Environment.TickCount64 / 1000.0;
                if (_progress != null && (now - _lastProgressSave) >= ProgressSaveInterval)
                {
                    _progress.Save(status.File, status.PositionMs, status.DurationMs);
                    _lastProgressSave = now;
                }
            }

            if (_prevFile != null && _prevFile != status.File)
                await OnStoppedAsync(_prevFile);
            _prevFile = status.File;
        }
        else if (status.State == 0)
        {
            _stoppedPolls++;
            if (_stoppedPolls >= 2 && _prevFile != null)
                await OnStoppedAsync(_prevFile);
        }
        else
        {
            _stoppedPolls = 0;
        }
    }

    private async Task OnStoppedAsync(string filePath)
    {
        var pct = _maxPct.GetValueOrDefault(filePath, 0.0);

        if (_progress != null)
        {
            var existing = _progress.Get(filePath);
            if (existing != null && existing.ContainsKey("duration_ms"))
            {
                var dur = Convert.ToInt32(existing["duration_ms"]);
                var pos = (int)(dur * pct);
                _progress.Save(filePath, pos, dur);
            }
        }

        if (pct >= _settings.WatchThreshold)
        {
            _logger.LogInformation("Archiving watched file ({Pct:P0}): {File}", pct, filePath);
            await ArchiveAsync(filePath);
        }

        _maxPct.Remove(filePath);
        _prevFile = null;
        _stoppedPolls = 0;
    }

    private Task ArchiveAsync(string filePath)
    {
        if (!File.Exists(filePath)) return Task.CompletedTask;

        foreach (var (primaryDir, archiveDir) in _dirPairs)
        {
            if (!filePath.StartsWith(primaryDir, StringComparison.OrdinalIgnoreCase))
                continue;

            var rel = Path.GetRelativePath(primaryDir, filePath);
            var dest = Path.Combine(archiveDir, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);

            try
            {
                File.Move(filePath, dest);
                _logger.LogInformation("Moved: {Source} -> {Dest}", filePath, dest);
            }
            catch (Exception ex)
            {
                _logger.LogError("Archive move failed: {Error}", ex.Message);
                return Task.CompletedTask;
            }

            // Move subtitle files
            var dir = Path.GetDirectoryName(filePath)!;
            var stem = Path.GetFileNameWithoutExtension(filePath);
            foreach (var sibling in Directory.EnumerateFiles(dir, stem + ".*"))
            {
                if (SubtitleExts.Contains(Path.GetExtension(sibling).ToLowerInvariant()))
                {
                    try { File.Move(sibling, Path.Combine(Path.GetDirectoryName(dest)!, Path.GetFileName(sibling))); }
                    catch { }
                }
            }

            var isMovie = primaryDir == _settings.MoviesDir;
            if (isMovie)
            {
                MoveRemnants(Path.GetDirectoryName(filePath)!, Path.GetDirectoryName(dest)!);
            }
            else
            {
                RemoveIfEmpty(Path.GetDirectoryName(filePath)!);
                var parentDir = Path.GetDirectoryName(Path.GetDirectoryName(filePath)!);
                if (parentDir != null) RemoveIfEmpty(parentDir);
            }
            return Task.CompletedTask;
        }

        return Task.CompletedTask;
    }

    private static void MoveRemnants(string srcFolder, string destFolder)
    {
        if (!Directory.Exists(srcFolder)) return;
        if (Directory.EnumerateFiles(srcFolder).Any(f => VideoExts.Contains(Path.GetExtension(f).ToLowerInvariant())))
            return;
        foreach (var f in Directory.EnumerateFiles(srcFolder))
        {
            try { File.Move(f, Path.Combine(destFolder, Path.GetFileName(f))); } catch { }
        }
        try { Directory.Delete(srcFolder); } catch { }
    }

    private static void RemoveIfEmpty(string folder)
    {
        if (!Directory.Exists(folder)) return;
        var hasVideo = Directory.EnumerateFiles(folder, "*", SearchOption.AllDirectories)
            .Any(f => VideoExts.Contains(Path.GetExtension(f).ToLowerInvariant()));
        if (!hasVideo)
        {
            try { Directory.Delete(folder, recursive: true); } catch { }
        }
    }
}
