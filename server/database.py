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
