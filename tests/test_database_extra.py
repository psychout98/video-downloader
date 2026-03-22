"""
Extra unit tests for database.py to cover init_db and _row_to_dict.

Tests cover:
- init_db() schema creation
- _row_to_dict() helper
- init_db() migration (adding stream_data column)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import aiosqlite

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.database import init_db, _row_to_dict, DB_PATH


# ── init_db ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestInitDb:
    async def test_creates_all_tables(self, tmp_path, monkeypatch):
        import server.database as db_mod
        db_path = tmp_path / "test_init.db"
        monkeypatch.setattr(db_mod, "DB_PATH", db_path)

        await init_db()

        async with aiosqlite.connect(db_path) as db:
            # Check jobs table
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
            ) as cursor:
                assert await cursor.fetchone() is not None

            # Check media_items table
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='media_items'"
            ) as cursor:
                assert await cursor.fetchone() is not None

            # Check watch_progress table
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='watch_progress'"
            ) as cursor:
                assert await cursor.fetchone() is not None

    async def test_creates_indexes(self, tmp_path, monkeypatch):
        import server.database as db_mod
        db_path = tmp_path / "test_indexes.db"
        monkeypatch.setattr(db_mod, "DB_PATH", db_path)

        await init_db()

        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_progress_updated'"
            ) as cursor:
                assert await cursor.fetchone() is not None

            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_progress_watched'"
            ) as cursor:
                assert await cursor.fetchone() is not None

    async def test_idempotent_call(self, tmp_path, monkeypatch):
        """Calling init_db() twice should not raise."""
        import server.database as db_mod
        db_path = tmp_path / "test_idempotent.db"
        monkeypatch.setattr(db_mod, "DB_PATH", db_path)

        await init_db()
        await init_db()  # Should not raise

    async def test_jobs_table_has_stream_data_column(self, tmp_path, monkeypatch):
        """init_db() adds stream_data column via migration."""
        import server.database as db_mod
        db_path = tmp_path / "test_stream_data.db"
        monkeypatch.setattr(db_mod, "DB_PATH", db_path)

        await init_db()

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("PRAGMA table_info(jobs)") as cursor:
                columns = [row[1] async for row in cursor]
                assert "stream_data" in columns


# ── _row_to_dict ────────────────────────────────────────────────────────


class TestRowToDict:
    def test_converts_row_to_dict(self):
        row = ("value1", 42, True)
        description = [("col_a",), ("col_b",), ("col_c",)]
        result = _row_to_dict(row, description)
        assert result == {"col_a": "value1", "col_b": 42, "col_c": True}

    def test_empty_row(self):
        row = ()
        description = []
        result = _row_to_dict(row, description)
        assert result == {}

    def test_single_column(self):
        row = ("only_value",)
        description = [("name",)]
        result = _row_to_dict(row, description)
        assert result == {"name": "only_value"}

    def test_none_values(self):
        row = (None, None)
        description = [("a",), ("b",)]
        result = _row_to_dict(row, description)
        assert result == {"a": None, "b": None}
