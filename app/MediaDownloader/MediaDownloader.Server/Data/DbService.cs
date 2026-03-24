using Microsoft.Data.Sqlite;
using MediaDownloader.Server.Configuration;

namespace MediaDownloader.Server.Data;

/// <summary>
/// SQLite database layer — mirrors server/database.py.
/// Opens/closes connections per operation (SQLite connections are cheap).
/// </summary>
public class DbService
{
    private readonly string _connectionString;

    public DbService(ServerSettings settings)
    {
        _connectionString = $"Data Source={settings.DbPath}";
    }

    // ------------------------------------------------------------------
    // Schema
    // ------------------------------------------------------------------

    public async Task InitAsync()
    {
        await using var db = new SqliteConnection(_connectionString);
        await db.OpenAsync();

        await ExecuteNonQuery(db, """
            CREATE TABLE IF NOT EXISTS jobs (
                id                TEXT PRIMARY KEY,
                query             TEXT NOT NULL,
                title             TEXT,
                year              INTEGER,
                imdb_id           TEXT,
                type              TEXT,
                season            INTEGER,
                episode           INTEGER,
                status            TEXT DEFAULT 'pending',
                progress          REAL DEFAULT 0.0,
                size_bytes        INTEGER,
                downloaded_bytes  INTEGER DEFAULT 0,
                quality           TEXT,
                torrent_name      TEXT,
                rd_torrent_id     TEXT,
                file_path         TEXT,
                error             TEXT,
                log               TEXT DEFAULT '',
                stream_data       TEXT,
                created_at        TEXT,
                updated_at        TEXT
            )
        """);

        await ExecuteNonQuery(db, """
            CREATE TABLE IF NOT EXISTS media_items (
                tmdb_id       INTEGER PRIMARY KEY,
                title         TEXT    NOT NULL,
                year          INTEGER,
                type          TEXT    NOT NULL,
                overview      TEXT,
                poster_path   TEXT,
                imdb_id       TEXT,
                folder_name   TEXT    NOT NULL,
                added_at      TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
        """);

        await ExecuteNonQuery(db, """
            CREATE TABLE IF NOT EXISTS watch_progress (
                tmdb_id       INTEGER NOT NULL,
                rel_path      TEXT    NOT NULL,
                position_ms   INTEGER NOT NULL DEFAULT 0,
                duration_ms   INTEGER NOT NULL DEFAULT 0,
                watched       BOOLEAN NOT NULL DEFAULT 0,
                updated_at    TEXT    NOT NULL,
                PRIMARY KEY (tmdb_id, rel_path),
                FOREIGN KEY (tmdb_id) REFERENCES media_items(tmdb_id)
            )
        """);

        await ExecuteNonQuery(db, """
            CREATE INDEX IF NOT EXISTS idx_progress_updated
            ON watch_progress(updated_at DESC)
        """);
        await ExecuteNonQuery(db, """
            CREATE INDEX IF NOT EXISTS idx_progress_watched
            ON watch_progress(watched, updated_at DESC)
        """);

        // Migration: add stream_data column if missing
        try
        {
            await ExecuteNonQuery(db, "ALTER TABLE jobs ADD COLUMN stream_data TEXT");
        }
        catch (SqliteException) { /* Column already exists */ }
    }

    // ------------------------------------------------------------------
    // Jobs
    // ------------------------------------------------------------------

    public async Task<Dictionary<string, object?>> CreateJobAsync(string query, string? streamData = null)
    {
        var jobId = Guid.NewGuid().ToString();
        var now = Now();

        await using var db = Open();
        await ExecuteNonQuery(db,
            "INSERT INTO jobs (id, query, stream_data, status, progress, downloaded_bytes, log, created_at, updated_at) " +
            "VALUES (@id, @query, @streamData, 'pending', 0.0, 0, '', @now, @now)",
            new SqliteParameter("@id", jobId),
            new SqliteParameter("@query", query.Trim()),
            new SqliteParameter("@streamData", (object?)streamData ?? DBNull.Value),
            new SqliteParameter("@now", now));

        return (await GetJobAsync(jobId))!;
    }

    public async Task UpdateJobAsync(string jobId, Dictionary<string, object?> fields)
    {
        if (fields.Count == 0) return;
        fields["updated_at"] = Now();

        var setClauses = fields.Keys.Select(k => $"{k} = @{k}").ToList();
        var sql = $"UPDATE jobs SET {string.Join(", ", setClauses)} WHERE id = @_id";

        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = sql;
        foreach (var (key, value) in fields)
            cmd.Parameters.AddWithValue($"@{key}", value ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@_id", jobId);
        await cmd.ExecuteNonQueryAsync();
    }

    public async Task AppendLogAsync(string jobId, string message)
    {
        await using var db = Open();
        await ExecuteNonQuery(db,
            "UPDATE jobs SET log = log || @msg, updated_at = @now WHERE id = @id",
            new SqliteParameter("@msg", message + "\n"),
            new SqliteParameter("@now", Now()),
            new SqliteParameter("@id", jobId));
    }

    public async Task<Dictionary<string, object?>?> GetJobAsync(string jobId)
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = "SELECT * FROM jobs WHERE id = @id";
        cmd.Parameters.AddWithValue("@id", jobId);
        using var reader = await cmd.ExecuteReaderAsync();
        return await reader.ReadAsync() ? ReadRow(reader) : null;
    }

    public async Task<List<Dictionary<string, object?>>> GetAllJobsAsync(int limit = 100)
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = "SELECT * FROM jobs ORDER BY created_at DESC LIMIT @limit";
        cmd.Parameters.AddWithValue("@limit", limit);
        return await ReadAll(cmd);
    }

    public async Task<List<Dictionary<string, object?>>> GetPendingJobsAsync()
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = "SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at ASC";
        return await ReadAll(cmd);
    }

    public async Task<bool> DeleteJobAsync(string jobId)
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = "DELETE FROM jobs WHERE id = @id";
        cmd.Parameters.AddWithValue("@id", jobId);
        return await cmd.ExecuteNonQueryAsync() > 0;
    }

    // ------------------------------------------------------------------
    // Media Items
    // ------------------------------------------------------------------

    public async Task UpsertMediaItemAsync(
        int tmdbId, string title, int? year, string mediaType, string folderName,
        string? overview = null, string? posterPath = null, string? imdbId = null)
    {
        var now = Now();
        await using var db = Open();
        await ExecuteNonQuery(db, """
            INSERT INTO media_items (tmdb_id, title, year, type, overview, poster_path,
                                     imdb_id, folder_name, added_at, updated_at)
            VALUES (@tmdbId, @title, @year, @type, @overview, @posterPath,
                    @imdbId, @folderName, @now, @now)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title=excluded.title, year=excluded.year, type=excluded.type,
                overview=excluded.overview, poster_path=excluded.poster_path,
                imdb_id=excluded.imdb_id, folder_name=excluded.folder_name,
                updated_at=excluded.updated_at
        """,
            new SqliteParameter("@tmdbId", tmdbId),
            new SqliteParameter("@title", title),
            new SqliteParameter("@year", (object?)year ?? DBNull.Value),
            new SqliteParameter("@type", mediaType),
            new SqliteParameter("@overview", (object?)overview ?? DBNull.Value),
            new SqliteParameter("@posterPath", (object?)posterPath ?? DBNull.Value),
            new SqliteParameter("@imdbId", (object?)imdbId ?? DBNull.Value),
            new SqliteParameter("@folderName", folderName),
            new SqliteParameter("@now", now));
    }

    public async Task<Dictionary<string, object?>?> GetMediaItemAsync(int tmdbId)
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = "SELECT * FROM media_items WHERE tmdb_id = @id";
        cmd.Parameters.AddWithValue("@id", tmdbId);
        using var reader = await cmd.ExecuteReaderAsync();
        return await reader.ReadAsync() ? ReadRow(reader) : null;
    }

    // ------------------------------------------------------------------
    // Watch Progress
    // ------------------------------------------------------------------

    public async Task<bool> SaveWatchProgressAsync(
        int tmdbId, string relPath, int positionMs, int durationMs, double watchThreshold = 0.85)
    {
        var now = Now();
        var watched = durationMs > 0 && (double)positionMs / durationMs >= watchThreshold;

        await using var db = Open();
        await ExecuteNonQuery(db, """
            INSERT INTO watch_progress (tmdb_id, rel_path, position_ms, duration_ms, watched, updated_at)
            VALUES (@tmdbId, @relPath, @posMs, @durMs, @watched, @now)
            ON CONFLICT(tmdb_id, rel_path) DO UPDATE SET
                position_ms=excluded.position_ms, duration_ms=excluded.duration_ms,
                watched=excluded.watched, updated_at=excluded.updated_at
        """,
            new SqliteParameter("@tmdbId", tmdbId),
            new SqliteParameter("@relPath", relPath),
            new SqliteParameter("@posMs", positionMs),
            new SqliteParameter("@durMs", durationMs),
            new SqliteParameter("@watched", watched),
            new SqliteParameter("@now", now));

        return watched;
    }

    public async Task<List<Dictionary<string, object?>>> GetWatchProgressAsync(int tmdbId, string? relPath = null)
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        if (relPath != null)
        {
            cmd.CommandText = "SELECT * FROM watch_progress WHERE tmdb_id = @id AND rel_path = @rel";
            cmd.Parameters.AddWithValue("@id", tmdbId);
            cmd.Parameters.AddWithValue("@rel", relPath);
        }
        else
        {
            cmd.CommandText = "SELECT * FROM watch_progress WHERE tmdb_id = @id ORDER BY rel_path";
            cmd.Parameters.AddWithValue("@id", tmdbId);
        }
        return await ReadAll(cmd);
    }

    public async Task<List<Dictionary<string, object?>>> GetContinueWatchingAsync(int limit = 20)
    {
        await using var db = Open();
        using var cmd = db.CreateCommand();
        cmd.CommandText = """
            SELECT wp.*, mi.title, mi.type, mi.poster_path, mi.year
            FROM watch_progress wp
            JOIN media_items mi ON wp.tmdb_id = mi.tmdb_id
            WHERE wp.watched = 0 AND wp.position_ms > 0
            ORDER BY wp.updated_at DESC
            LIMIT @limit
        """;
        cmd.Parameters.AddWithValue("@limit", limit);
        return await ReadAll(cmd);
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    private SqliteConnection Open()
    {
        var conn = new SqliteConnection(_connectionString);
        conn.Open();
        return conn;
    }

    private static string Now() => DateTime.UtcNow.ToString("O");

    private static async Task ExecuteNonQuery(SqliteConnection db, string sql, params SqliteParameter[] parameters)
    {
        using var cmd = db.CreateCommand();
        cmd.CommandText = sql;
        foreach (var p in parameters) cmd.Parameters.Add(p);
        await cmd.ExecuteNonQueryAsync();
    }

    private static Dictionary<string, object?> ReadRow(SqliteDataReader reader)
    {
        var dict = new Dictionary<string, object?>();
        for (int i = 0; i < reader.FieldCount; i++)
        {
            dict[reader.GetName(i)] = reader.IsDBNull(i) ? null : reader.GetValue(i);
        }
        return dict;
    }

    private static async Task<List<Dictionary<string, object?>>> ReadAll(SqliteCommand cmd)
    {
        var results = new List<Dictionary<string, object?>>();
        using var reader = await cmd.ExecuteReaderAsync();
        while (await reader.ReadAsync())
            results.Add(ReadRow(reader));
        return results;
    }
}
