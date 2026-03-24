"""
SQLite database layer using aiosqlite.

Schema
------
jobs
  id              TEXT  PRIMARY KEY  (UUID)
  query           TEXT               original user query
  title           TEXT               resolved title from TMDB
  year            INTEGER
  imdb_id         TEXT
  type            TEXT               movie | tv | anime
  season          INTEGER            null for movies
  episode         INTEGER            null for full-season downloads
  status          TEXT               see JobStatus enum
  progress        REAL               0.0 – 1.0
  size_bytes      INTEGER
  downloaded_bytes INTEGER
  quality         TEXT               human-readable quality string
  torrent_name    TEXT               raw torrent filename
  rd_torrent_id   TEXT               Real-Debrid torrent id
  file_path       TEXT               final library path after organising
  error           TEXT
  log             TEXT               newline-delimited progress log
  created_at      TEXT               ISO datetime
  updated_at      TEXT               ISO datetime

media_items
  tmdb_id         INTEGER PRIMARY KEY  (TMDB ID — stable unique key)
  title           TEXT                  clean display title
  year            INTEGER               release year
  type            TEXT                  movie | tv | anime
  overview        TEXT                  TMDB synopsis
  poster_path     TEXT                  TMDB poster path (e.g. /abc123.jpg)
  imdb_id         TEXT                  IMDb ID if available
  folder_name     TEXT                  current folder name: "Title [tmdb_id]"
  added_at        TEXT                  ISO timestamp of first discovery
  updated_at      TEXT                  ISO timestamp of last metadata refresh

watch_progress
  tmdb_id         INTEGER               FK → media_items
  rel_path        TEXT                  relative path: "S01E01 - Pilot.mkv"
  position_ms     INTEGER               playback position
  duration_ms     INTEGER               total duration
  watched         BOOLEAN               true when position >= threshold
  updated_at      TEXT                  ISO timestamp
  PRIMARY KEY (tmdb_id, rel_path)
"""
from __future__ import annotations

import uuid
import aiosqlite
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent.parent / "media_downloader.db"


class JobStatus(str, Enum):
    PENDING = "pending"
    SEARCHING = "searching"
    FOUND = "found"
    ADDING_TO_RD = "adding_to_rd"
    WAITING_FOR_RD = "waiting_for_rd"
    DOWNLOADING = "downloading"
    ORGANIZING = "organizing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
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
        """)

        # --- Library tables ---
        await db.execute("""
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
        """)

        await db.execute("""
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
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_progress_updated
            ON watch_progress(updated_at DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_progress_watched
            ON watch_progress(watched, updated_at DESC)
        """)

        await db.commit()

        # Migration: add stream_data column to existing databases
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN stream_data TEXT")
            await db.commit()
        except Exception:
            pass  # Column already exists — fine


def _row_to_dict(row, description) -> dict:
    return {description[i][0]: row[i] for i in range(len(description))}


async def create_job(query: str, stream_data: Optional[str] = None) -> dict:
    job_id = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO jobs (id, query, stream_data, status, progress, downloaded_bytes, log, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', 0.0, 0, '', ?, ?)",
            (job_id, query.strip(), stream_data, now, now),
        )
        await db.commit()
    return await get_job(job_id)


async def update_job(job_id: str, **kwargs: Any) -> None:
    """Update arbitrary fields on a job row."""
    if not kwargs:
        return
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        await db.commit()


async def append_log(job_id: str, message: str) -> None:
    """Append a line to the job's running log."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET log = log || ?, updated_at = ? WHERE id = ?",
            (f"{message}\n", _now(), job_id),
        )
        await db.commit()


async def get_job(job_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_jobs(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_pending_jobs() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_job(job_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await db.commit()
        return cursor.rowcount > 0


# ── Media Items ──────────────────────────────────────────────────────────────

async def upsert_media_item(
    tmdb_id: int,
    title: str,
    year: Optional[int],
    media_type: str,
    folder_name: str,
    overview: Optional[str] = None,
    poster_path: Optional[str] = None,
    imdb_id: Optional[str] = None,
) -> None:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO media_items (tmdb_id, title, year, type, overview, poster_path,
                                     imdb_id, folder_name, added_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title=excluded.title, year=excluded.year, type=excluded.type,
                overview=excluded.overview, poster_path=excluded.poster_path,
                imdb_id=excluded.imdb_id, folder_name=excluded.folder_name,
                updated_at=excluded.updated_at
        """, (tmdb_id, title, year, media_type, overview, poster_path,
              imdb_id, folder_name, now, now))
        await db.commit()


async def get_media_item(tmdb_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM media_items WHERE tmdb_id = ?", (tmdb_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_media_items(media_type: Optional[str] = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if media_type:
            async with db.execute(
                "SELECT * FROM media_items WHERE type = ? ORDER BY title", (media_type,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute("SELECT * FROM media_items ORDER BY title") as cur:
                return [dict(r) for r in await cur.fetchall()]


# ── Watch Progress ───────────────────────────────────────────────────────────

async def save_watch_progress(
    tmdb_id: int,
    rel_path: str,
    position_ms: int,
    duration_ms: int,
    watch_threshold: float = 0.85,
) -> bool:
    """Save progress. Returns True if the item is now marked as watched."""
    now = _now()
    watched = (duration_ms > 0 and position_ms / duration_ms >= watch_threshold)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO watch_progress (tmdb_id, rel_path, position_ms, duration_ms, watched, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id, rel_path) DO UPDATE SET
                position_ms=excluded.position_ms, duration_ms=excluded.duration_ms,
                watched=excluded.watched, updated_at=excluded.updated_at
        """, (tmdb_id, rel_path, position_ms, duration_ms, watched, now))
        await db.commit()
    return watched


async def get_watch_progress(tmdb_id: int, rel_path: Optional[str] = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if rel_path:
            async with db.execute(
                "SELECT * FROM watch_progress WHERE tmdb_id = ? AND rel_path = ?",
                (tmdb_id, rel_path),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM watch_progress WHERE tmdb_id = ? ORDER BY rel_path",
                (tmdb_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


# Convenience aliases used by watch_tracker
save_progress = save_watch_progress


async def get_progress(tmdb_id: int, rel_path: Optional[str] = None) -> Optional[dict]:
    """Return a single progress dict (or None) — convenience wrapper."""
    rows = await get_watch_progress(tmdb_id, rel_path)
    return rows[0] if rows else None


async def get_continue_watching(limit: int = 20) -> list[dict]:
    """Return items with partial progress (not fully watched), most recent first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT wp.*, mi.title, mi.type, mi.poster_path, mi.year
            FROM watch_progress wp
            JOIN media_items mi ON wp.tmdb_id = mi.tmdb_id
            WHERE wp.watched = 0 AND wp.position_ms > 0
            ORDER BY wp.updated_at DESC
            LIMIT ?
        """, (limit,)) as cur:
            return [dict(r) for r in await cur.fetchall()]
