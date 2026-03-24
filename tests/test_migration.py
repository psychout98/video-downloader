"""
Tests for the one-time migration module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch settings before importing migration module
os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")


class TestCheckMigrationNeeded:
    @pytest.mark.asyncio
    async def test_returns_true_when_not_migrated(self):
        with patch("server.core.migration.settings") as mock_settings:
            mock_settings.MIGRATED = False
            from server.core.migration import check_migration_needed
            assert await check_migration_needed() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_migrated(self):
        with patch("server.core.migration.settings") as mock_settings:
            mock_settings.MIGRATED = True
            from server.core.migration import check_migration_needed
            assert await check_migration_needed() is False


class TestParseTitleYear:
    def test_parses_title_with_year(self):
        from server.core.migration import _parse_title_year
        title, year = _parse_title_year("Inception (2010)")
        assert title == "Inception"
        assert year == 2010

    def test_parses_title_without_year(self):
        from server.core.migration import _parse_title_year
        title, year = _parse_title_year("Breaking Bad")
        assert title == "Breaking Bad"
        assert year is None

    def test_parses_title_with_extra_spaces(self):
        from server.core.migration import _parse_title_year
        title, year = _parse_title_year("  Inception  (2010) ")
        assert title == "Inception"
        assert year == 2010


class TestSafeFolder:
    def test_replaces_colon(self):
        from server.core.migration import _safe_folder
        assert _safe_folder("Star Wars: A New Hope") == "Star Wars - A New Hope"

    def test_removes_illegal_chars(self):
        from server.core.migration import _safe_folder
        result = _safe_folder('File<>Name|Test?')
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert "?" not in result


class TestMigrateLibraryData:
    @pytest.mark.asyncio
    async def test_reads_library_json_and_registers_items(self, tmp_path):
        from server.core.migration import _migrate_library_data

        # Create a mock library.json
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        library_json = data_dir / "library.json"
        library_json.write_text(json.dumps([
            {"title": "Inception", "year": 2010, "type": "movie"},
            {"title": "Breaking Bad", "year": 2008, "type": "tv"},
        ]))

        # Mock tmdb client that returns IDs
        tmdb = AsyncMock()

        async def fake_get(endpoint, params=None):
            title = params.get("query", "")
            if "inception" in title.lower():
                return {"results": [{"id": 27205, "title": "Inception", "popularity": 100}]}
            elif "breaking" in title.lower():
                return {"results": [{"id": 1396, "name": "Breaking Bad", "popularity": 200}]}
            return {"results": []}

        tmdb._get = fake_get

        summary = {"library_items_migrated": 0, "errors": []}

        with patch("server.core.migration.settings") as mock_settings, \
             patch("server.core.migration.upsert_media_item") as mock_upsert:
            mock_settings.POSTERS_DIR = str(data_dir / "posters")
            mock_upsert.return_value = None

            await _migrate_library_data(tmdb, summary)

        assert summary["library_items_migrated"] == 2
        assert len(summary["errors"]) == 0

    @pytest.mark.asyncio
    async def test_skips_items_without_tmdb_match(self, tmp_path):
        from server.core.migration import _migrate_library_data

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        library_json = data_dir / "library.json"
        library_json.write_text(json.dumps([
            {"title": "Unknown Movie XYZ", "year": 2099, "type": "movie"},
        ]))

        tmdb = AsyncMock()

        async def fake_get(endpoint, params=None):
            return {"results": []}

        tmdb._get = fake_get

        summary = {"library_items_migrated": 0, "errors": []}

        with patch("server.core.migration.settings") as mock_settings:
            mock_settings.POSTERS_DIR = str(data_dir / "posters")
            await _migrate_library_data(tmdb, summary)

        assert summary["library_items_migrated"] == 0
        assert len(summary["errors"]) == 1


class TestMigratePosters:
    @pytest.mark.asyncio
    async def test_renames_poster_files(self, tmp_path):
        from server.core.migration import _migrate_posters

        posters_dir = tmp_path / "posters"
        posters_dir.mkdir()
        (posters_dir / "Inception (2010).jpg").write_bytes(b"fake poster data")
        (posters_dir / "Breaking Bad.jpg").write_bytes(b"fake poster data")

        summary = {"posters_renamed": 0, "errors": []}

        with patch("server.core.migration.settings") as mock_settings, \
             patch("server.core.migration.DB_PATH", tmp_path / "test.db"):
            mock_settings.POSTERS_DIR = str(posters_dir)

            # Create a fake db with media items
            import aiosqlite
            async with aiosqlite.connect(tmp_path / "test.db") as db:
                await db.execute("""
                    CREATE TABLE media_items (
                        tmdb_id INTEGER PRIMARY KEY, title TEXT, year INTEGER,
                        type TEXT, overview TEXT, poster_path TEXT, imdb_id TEXT,
                        folder_name TEXT, added_at TEXT, updated_at TEXT
                    )
                """)
                await db.execute(
                    "INSERT INTO media_items VALUES (27205, 'Inception', 2010, 'movie', NULL, NULL, NULL, 'Inception [27205]', '', '')"
                )
                await db.execute(
                    "INSERT INTO media_items VALUES (1396, 'Breaking Bad', 2008, 'tv', NULL, NULL, NULL, 'Breaking Bad [1396]', '', '')"
                )
                await db.commit()

            await _migrate_posters(summary)

        assert summary["posters_renamed"] == 2
        assert (posters_dir / "27205.jpg").exists()
        assert (posters_dir / "1396.jpg").exists()
        assert not (posters_dir / "Inception (2010).jpg").exists()

    @pytest.mark.asyncio
    async def test_skips_already_numeric_posters(self, tmp_path):
        from server.core.migration import _migrate_posters

        posters_dir = tmp_path / "posters"
        posters_dir.mkdir()
        (posters_dir / "27205.jpg").write_bytes(b"already migrated")

        summary = {"posters_renamed": 0, "errors": []}

        with patch("server.core.migration.settings") as mock_settings, \
             patch("server.core.migration.DB_PATH", tmp_path / "test.db"):
            mock_settings.POSTERS_DIR = str(posters_dir)

            import aiosqlite
            async with aiosqlite.connect(tmp_path / "test.db") as db:
                await db.execute("""
                    CREATE TABLE media_items (
                        tmdb_id INTEGER PRIMARY KEY, title TEXT, year INTEGER,
                        type TEXT, overview TEXT, poster_path TEXT, imdb_id TEXT,
                        folder_name TEXT, added_at TEXT, updated_at TEXT
                    )
                """)
                await db.commit()

            await _migrate_posters(summary)

        assert summary["posters_renamed"] == 0


class TestMigrateWatchProgress:
    @pytest.mark.asyncio
    async def test_migrates_progress_entries(self, tmp_path):
        from server.core.migration import _migrate_watch_progress

        # Use platform-appropriate paths
        movies_dir = tmp_path / "Media" / "Movies"
        movies_dir.mkdir(parents=True)
        movie_folder = movies_dir / "Inception (2010)"
        movie_folder.mkdir()
        movie_file = movie_folder / "Inception (2010).mkv"
        movie_file.write_bytes(b"fake")

        progress_file = tmp_path / "playback.json"
        progress_data = {
            str(movie_file): {
                "position_ms": 5400000,
                "duration_ms": 8880000,
                "updated_at": 1700000000.0,
            }
        }
        progress_file.write_text(json.dumps(progress_data))

        summary = {"progress_entries_migrated": 0, "errors": []}

        with patch("server.core.migration.settings") as mock_settings, \
             patch("server.core.migration.DB_PATH", tmp_path / "test.db"), \
             patch("server.core.migration.save_watch_progress") as mock_save:
            mock_settings.PROGRESS_FILE = str(progress_file)
            mock_settings.MOVIES_DIR = str(movies_dir)
            mock_settings.TV_DIR = str(tmp_path / "Media" / "TV Shows")
            mock_settings.ANIME_DIR = str(tmp_path / "Media" / "Anime")
            mock_settings.MOVIES_DIR_ARCHIVE = str(tmp_path / "Archive" / "Movies")
            mock_settings.TV_DIR_ARCHIVE = str(tmp_path / "Archive" / "TV Shows")
            mock_settings.ANIME_DIR_ARCHIVE = str(tmp_path / "Archive" / "Anime")
            mock_settings.WATCH_THRESHOLD = 0.85
            mock_save.return_value = False

            # Create a fake db with media items
            import aiosqlite
            async with aiosqlite.connect(tmp_path / "test.db") as db:
                await db.execute("""
                    CREATE TABLE media_items (
                        tmdb_id INTEGER PRIMARY KEY, title TEXT, year INTEGER,
                        type TEXT, overview TEXT, poster_path TEXT, imdb_id TEXT,
                        folder_name TEXT, added_at TEXT, updated_at TEXT
                    )
                """)
                await db.execute(
                    "INSERT INTO media_items VALUES (27205, 'Inception', 2010, 'movie', NULL, NULL, NULL, 'Inception [27205]', '', '')"
                )
                await db.commit()

            await _migrate_watch_progress(summary)

        assert summary["progress_entries_migrated"] == 1


class TestRunMigration:
    @pytest.mark.asyncio
    async def test_full_migration_runs_all_steps(self, tmp_path):
        from server.core.migration import run_migration

        with patch("server.core.migration._migrate_library_data") as mock_lib, \
             patch("server.core.migration._migrate_watch_progress") as mock_wp, \
             patch("server.core.migration._migrate_posters") as mock_posters, \
             patch("server.core.migration._migrate_filesystem") as mock_fs, \
             patch("server.core.migration._migrate_config") as mock_config, \
             patch("server.core.migration._set_env_key") as mock_env:

            summary = await run_migration(tmdb_client=AsyncMock())

        mock_lib.assert_called_once()
        mock_wp.assert_called_once()
        mock_posters.assert_called_once()
        mock_fs.assert_called_once()
        mock_config.assert_called_once()
        mock_env.assert_called_once_with("MIGRATED", "True")
        assert summary["config_migrated"] is True
