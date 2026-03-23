using System.Text.Json;

namespace MediaDownloader.Server.Core;

/// <summary>
/// Persistent per-file playback position store (JSON file).
/// Mirrors server/core/progress_store.py.
/// </summary>
public class ProgressStore
{
    private readonly string _path;
    private readonly object _lock = new();
    private Dictionary<string, Dictionary<string, object>> _data = new();
    private readonly ILogger? _logger;

    public ProgressStore(string path, ILogger? logger = null)
    {
        _path = path;
        _logger = logger;
        Load();
    }

    public Dictionary<string, object>? Get(string filePath)
    {
        lock (_lock)
        {
            return _data.GetValueOrDefault(filePath);
        }
    }

    public void Save(string filePath, int positionMs, int durationMs)
    {
        lock (_lock)
        {
            _data[filePath] = new()
            {
                ["position_ms"] = positionMs,
                ["duration_ms"] = durationMs,
                ["updated_at"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            };
            Write();
        }
    }

    public double Pct(string filePath)
    {
        var d = Get(filePath);
        if (d == null) return 0.0;
        var dur = Convert.ToInt64(d.GetValueOrDefault("duration_ms", 0));
        if (dur == 0) return 0.0;
        var pos = Convert.ToInt64(d.GetValueOrDefault("position_ms", 0));
        return Math.Min((double)pos / dur, 1.0);
    }

    private void Load()
    {
        try
        {
            if (File.Exists(_path))
            {
                var json = File.ReadAllText(_path);
                _data = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, object>>>(json) ?? new();
                _logger?.LogInformation("Loaded progress store ({Count} entries)", _data.Count);
            }
        }
        catch (Exception ex)
        {
            _logger?.LogWarning("Could not load progress store: {Error}", ex.Message);
            _data = new();
        }
    }

    private void Write()
    {
        try
        {
            var dir = Path.GetDirectoryName(_path);
            if (dir != null) Directory.CreateDirectory(dir);
            var tmp = _path + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(_data, new JsonSerializerOptions { WriteIndented = true }));
            File.Move(tmp, _path, overwrite: true);
        }
        catch (Exception ex)
        {
            _logger?.LogWarning("Could not write progress store: {Error}", ex.Message);
        }
    }
}
