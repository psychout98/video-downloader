"""
Extra unit tests for library_manager.py covering helper functions
not directly tested through the LibraryManager.scan() integration tests.

Tests cover:
- _find_poster (poster lookup by tmdb_id)
- _merge_entries (media + archive merging)
- _scan_directory (single directory scanning)
- LibraryManager.refresh() (async refresh pipeline)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.core.library_manager import (
    _find_poster,
    _merge_entries,
    _scan_directory,
    LibraryManager,
)


# ── _find_poster ────────────────────────────────────────────────────────


class TestFindPoster:
    def test_finds_jpg_poster(self, tmp_path):
        (tmp_path / "27205.jpg").write_bytes(b"\xFF\xD8")
        result = _find_poster(tmp_path, 27205)
        assert result is not None
        assert "27205.jpg" in result

    def test_finds_png_poster(self, tmp_path):
        (tmp_path / "27205.png").write_bytes(b"\x89PNG")
        result = _find_poster(tmp_path, 27205)
        assert result is not None
        assert "27205.png" in result

    def test_finds_webp_poster(self, tmp_path):
        (tmp_path / "27205.webp").write_bytes(b"RIFF")
        result = _find_poster(tmp_path, 27205)
        assert result is not None

    def test_returns_none_when_no_poster(self, tmp_path):
        result = _find_poster(tmp_path, 99999)
        assert result is None

    def test_returns_none_for_empty_dir(self, tmp_path):
        result = _find_poster(tmp_path, 1)
        assert result is None

    def test_prefers_jpg_over_other_extensions(self, tmp_path):
        """First match wins — .jpg is checked first."""
        (tmp_path / "100.jpg").write_bytes(b"jpg")
        (tmp_path / "100.png").write_bytes(b"png")
        result = _find_poster(tmp_path, 100)
        assert result.endswith(".jpg")


# ── _merge_entries ──────────────────────────────────────────────────────


class TestMergeEntries:
    def test_merge_disjoint_entries(self):
        media = [
            {"tmdb_id": 1, "folder_name": "A [1]", "file_count": 2, "size_bytes": 100,
             "modified_at": 1000, "poster": None},
        ]
        archive = [
            {"tmdb_id": 2, "folder_name": "B [2]", "file_count": 3, "size_bytes": 200,
             "modified_at": 900, "poster": None},
        ]
        result = _merge_entries(media, archive)
        assert len(result) == 2
        ids = {r["tmdb_id"] for r in result}
        assert ids == {1, 2}

    def test_merge_same_tmdb_id_combines_counts(self):
        media = [
            {"tmdb_id": 1, "folder_name": "Show [1]", "file_count": 2, "size_bytes": 100,
             "modified_at": 1000, "poster": None},
        ]
        archive = [
            {"tmdb_id": 1, "folder_name": "Show [1]", "file_count": 5, "size_bytes": 500,
             "modified_at": 900, "poster": "/poster.jpg"},
        ]
        result = _merge_entries(media, archive)
        assert len(result) == 1
        assert result[0]["file_count"] == 7
        assert result[0]["size_bytes"] == 600
        assert result[0]["location"] == "both"
        assert result[0]["modified_at"] == 1000  # max

    def test_merge_picks_poster_from_archive_if_media_has_none(self):
        media = [
            {"tmdb_id": 1, "folder_name": "Show [1]", "file_count": 1, "size_bytes": 50,
             "modified_at": 1000, "poster": None},
        ]
        archive = [
            {"tmdb_id": 1, "folder_name": "Show [1]", "file_count": 2, "size_bytes": 100,
             "modified_at": 900, "poster": "/path/poster.jpg"},
        ]
        result = _merge_entries(media, archive)
        assert result[0]["poster"] == "/path/poster.jpg"

    def test_merge_empty_lists(self):
        result = _merge_entries([], [])
        assert result == []

    def test_merge_uses_folder_name_as_key_for_no_tmdb_id(self):
        media = [
            {"tmdb_id": None, "folder_name": "Legacy Movie", "file_count": 1,
             "size_bytes": 50, "modified_at": 1000, "poster": None},
        ]
        archive = [
            {"tmdb_id": None, "folder_name": "Legacy Movie", "file_count": 1,
             "size_bytes": 50, "modified_at": 900, "poster": None},
        ]
        result = _merge_entries(media, archive)
        assert len(result) == 1
        assert result[0]["location"] == "both"

    def test_merge_archive_only_item_has_archive_location(self):
        result = _merge_entries([], [
            {"tmdb_id": 1, "folder_name": "A [1]", "file_count": 1, "size_bytes": 50,
             "modified_at": 900, "poster": None},
        ])
        assert len(result) == 1
        assert result[0]["location"] == "archive"


# ── _scan_directory ─────────────────────────────────────────────────────


class TestScanDirectory:
    def test_scans_folder_with_tmdb_id(self, tmp_path):
        base = tmp_path / "media"
        base.mkdir()
        show_dir = base / "Show [100]"
        show_dir.mkdir()
        (show_dir / "S01E01.mkv").write_bytes(b"video")

        posters = tmp_path / "posters"
        posters.mkdir()

        result = _scan_directory(base, posters, "media")
        assert len(result) == 1
        assert result[0]["tmdb_id"] == 100
        assert result[0]["storage"] == "media"

    def test_skips_hidden_folders(self, tmp_path):
        base = tmp_path / "media"
        base.mkdir()
        hidden = base / ".hidden"
        hidden.mkdir()
        (hidden / "video.mkv").write_bytes(b"v")

        result = _scan_directory(base, tmp_path, "media")
        assert result == []

    def test_skips_folders_without_videos(self, tmp_path):
        base = tmp_path / "media"
        base.mkdir()
        folder = base / "Empty [999]"
        folder.mkdir()
        (folder / "readme.txt").write_text("no videos")

        result = _scan_directory(base, tmp_path, "media")
        assert result == []

    def test_nonexistent_directory_returns_empty(self, tmp_path):
        result = _scan_directory(tmp_path / "nope", tmp_path, "media")
        assert result == []

    def test_scans_folder_without_tmdb_id(self, tmp_path):
        base = tmp_path / "media"
        base.mkdir()
        folder = base / "Inception (2010)"
        folder.mkdir()
        (folder / "movie.mkv").write_bytes(b"v")

        result = _scan_directory(base, tmp_path / "posters", "media")
        assert len(result) == 1
        assert result[0]["tmdb_id"] is None
        assert result[0]["year"] == 2010

    def test_counts_multiple_video_files(self, tmp_path):
        base = tmp_path / "media"
        base.mkdir()
        show_dir = base / "Show [100]"
        show_dir.mkdir()
        (show_dir / "S01E01.mkv").write_bytes(b"x" * 100)
        (show_dir / "S01E02.mkv").write_bytes(b"x" * 200)
        (show_dir / "S01E03.mp4").write_bytes(b"x" * 300)

        result = _scan_directory(base, tmp_path, "media")
        assert result[0]["file_count"] == 3
        assert result[0]["size_bytes"] == 600


# ── LibraryManager.refresh ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestLibraryManagerRefresh:
    async def test_refresh_upserts_resolved_folders(self, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir()
        (show_dir / "S01E01.mkv").write_bytes(b"video")

        posters_dir = tmp_path / "posters"
        posters_dir.mkdir()
        # Create existing poster so it doesn't try to download
        (posters_dir / "100.jpg").write_bytes(b"\xFF\xD8")

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(posters_dir)

            manager = LibraryManager(cache_ttl=0)

            mock_tmdb = AsyncMock()
            mock_tmdb.fuzzy_resolve = AsyncMock(return_value=("Show", 2020, "/poster.jpg"))

            with patch("server.database.upsert_media_item", new_callable=AsyncMock) as mock_upsert:
                summary = await manager.refresh(mock_tmdb)

        assert summary["added"] >= 1
        mock_upsert.assert_called()

    async def test_refresh_skips_folders_without_tmdb_id(self, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        legacy = media_dir / "Old Movie (2010)"
        legacy.mkdir()
        (legacy / "movie.mkv").write_bytes(b"video")

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")
            (tmp_path / "posters").mkdir()

            manager = LibraryManager(cache_ttl=0)
            mock_tmdb = AsyncMock()

            with patch("server.database.upsert_media_item", new_callable=AsyncMock) as mock_upsert:
                summary = await manager.refresh(mock_tmdb)

        # Unresolved folders should appear in errors
        assert len(summary["errors"]) > 0

    async def test_refresh_handles_empty_directories(self, tmp_path):
        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")
            (tmp_path / "posters").mkdir()

            manager = LibraryManager(cache_ttl=0)
            mock_tmdb = AsyncMock()

            summary = await manager.refresh(mock_tmdb)
            assert summary["added"] == 0
            assert summary["errors"] == []
