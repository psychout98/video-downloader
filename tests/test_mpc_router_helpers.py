"""
Unit tests for MPC router helper functions (server/routers/mpc.py).

Tests cover:
- _resolve_media_context (tmdb_id + episode parsing from file path)
- _resolve_file_path (tmdb_id + rel_path → absolute path)
- _get_adjacent_episode (next/prev episode in folder)
- _make_playlist (temporary .m3u creation)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.routers.mpc import (
    _resolve_media_context,
    _resolve_file_path,
    _get_adjacent_episode,
    _make_playlist,
)


# ── _resolve_media_context ──────────────────────────────────────────────


class TestResolveMediaContext:
    def test_extracts_tmdb_id_and_episode(self):
        with patch("server.routers.mpc.state") as mock_state:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = [
                {"tmdb_id": 1396, "title": "Breaking Bad", "type": "tv"}
            ]

            result = _resolve_media_context(
                r"C:\Media\Breaking Bad [1396]\S01E03 - And the Bag's in the River.mkv"
            )
            assert result is not None
            assert result["tmdb_id"] == 1396
            assert result["title"] == "Breaking Bad"
            assert result["type"] == "tv"
            assert result["season"] == 1
            assert result["episode"] == 3
            assert result["poster_url"] == "/api/library/1396/poster"

    def test_movie_file_no_episode(self):
        with patch("server.routers.mpc.state") as mock_state:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = [
                {"tmdb_id": 27205, "title": "Inception", "type": "movie"}
            ]

            result = _resolve_media_context(
                r"C:\Media\Inception [27205]\Inception (2010).mkv"
            )
            assert result is not None
            assert result["tmdb_id"] == 27205
            assert result["season"] is None
            assert result["episode"] is None

    def test_empty_path_returns_none(self):
        assert _resolve_media_context("") is None

    def test_no_bracket_id_returns_none(self):
        assert _resolve_media_context(r"C:\Media\Random Movie\video.mkv") is None

    def test_tmdb_id_not_in_library_still_returns_context(self):
        with patch("server.routers.mpc.state") as mock_state:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = []

            result = _resolve_media_context(
                r"C:\Media\Unknown [99999]\S01E01 - Test.mkv"
            )
            assert result is not None
            assert result["tmdb_id"] == 99999
            assert result["title"] == ""
            assert result["type"] == ""

    def test_none_library_returns_context_with_empty_title(self):
        with patch("server.routers.mpc.state") as mock_state:
            mock_state.library = None

            result = _resolve_media_context(
                r"C:\Media\Show [100]\S01E01 - Pilot.mkv"
            )
            assert result is not None
            assert result["tmdb_id"] == 100
            assert result["title"] == ""


# ── _resolve_file_path ──────────────────────────────────────────────────


class TestResolveFilePath:
    def test_finds_file_in_media_dir(self, tmp_path):
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        video = show_dir / "S01E01 - Pilot.mkv"
        video.write_bytes(b"video")

        with patch("server.routers.mpc.state") as mock_state, \
             patch("server.routers.mpc.settings") as mock_settings:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = [
                {"tmdb_id": 100, "folder_name": "Show [100]"}
            ]
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            result = _resolve_file_path(100, "S01E01 - Pilot.mkv")
            assert result == str(video)

    def test_finds_file_in_archive_dir(self, tmp_path):
        archive_dir = tmp_path / "archive"
        show_dir = archive_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        video = show_dir / "S01E01 - Pilot.mkv"
        video.write_bytes(b"video")

        with patch("server.routers.mpc.state") as mock_state, \
             patch("server.routers.mpc.settings") as mock_settings:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = [
                {"tmdb_id": 100, "folder_name": "Show [100]"}
            ]
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(archive_dir)

            result = _resolve_file_path(100, "S01E01 - Pilot.mkv")
            assert result == str(video)

    def test_returns_none_for_missing_file(self, tmp_path):
        with patch("server.routers.mpc.state") as mock_state, \
             patch("server.routers.mpc.settings") as mock_settings:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = [
                {"tmdb_id": 100, "folder_name": "Show [100]"}
            ]
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            result = _resolve_file_path(100, "S01E01.mkv")
            assert result is None

    def test_unknown_tmdb_id_uses_fallback_folder(self, tmp_path):
        with patch("server.routers.mpc.state") as mock_state, \
             patch("server.routers.mpc.settings") as mock_settings:
            mock_state.library = MagicMock()
            mock_state.library.scan.return_value = []
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            result = _resolve_file_path(99999, "video.mkv")
            assert result is None

    def test_none_library_uses_fallback(self, tmp_path):
        with patch("server.routers.mpc.state") as mock_state, \
             patch("server.routers.mpc.settings") as mock_settings:
            mock_state.library = None
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            result = _resolve_file_path(100, "video.mkv")
            assert result is None


# ── _get_adjacent_episode ───────────────────────────────────────────────


class TestGetAdjacentEpisode:
    def test_next_episode(self, tmp_path):
        (tmp_path / "S01E01 - Pilot.mkv").write_bytes(b"ep1")
        (tmp_path / "S01E02 - Second.mkv").write_bytes(b"ep2")
        (tmp_path / "S01E03 - Third.mkv").write_bytes(b"ep3")

        current = str(tmp_path / "S01E01 - Pilot.mkv")
        result = _get_adjacent_episode(current, +1)
        assert result is not None
        assert "S01E02" in result

    def test_prev_episode(self, tmp_path):
        (tmp_path / "S01E01 - Pilot.mkv").write_bytes(b"ep1")
        (tmp_path / "S01E02 - Second.mkv").write_bytes(b"ep2")

        current = str(tmp_path / "S01E02 - Second.mkv")
        result = _get_adjacent_episode(current, -1)
        assert result is not None
        assert "S01E01" in result

    def test_no_next_at_end_of_list(self, tmp_path):
        (tmp_path / "S01E01 - Pilot.mkv").write_bytes(b"ep1")
        (tmp_path / "S01E02 - Second.mkv").write_bytes(b"ep2")

        current = str(tmp_path / "S01E02 - Second.mkv")
        result = _get_adjacent_episode(current, +1)
        assert result is None

    def test_no_prev_at_start_of_list(self, tmp_path):
        (tmp_path / "S01E01 - Pilot.mkv").write_bytes(b"ep1")

        current = str(tmp_path / "S01E01 - Pilot.mkv")
        result = _get_adjacent_episode(current, -1)
        assert result is None

    def test_empty_path_returns_none(self):
        assert _get_adjacent_episode("", +1) is None

    def test_ignores_non_video_files(self, tmp_path):
        (tmp_path / "S01E01.mkv").write_bytes(b"ep1")
        (tmp_path / "S01E02.mkv").write_bytes(b"ep2")
        (tmp_path / "info.nfo").write_text("metadata")
        (tmp_path / "poster.jpg").write_bytes(b"img")

        current = str(tmp_path / "S01E01.mkv")
        result = _get_adjacent_episode(current, +1)
        assert result is not None
        assert "S01E02" in result

    def test_file_not_in_folder_returns_none(self, tmp_path):
        (tmp_path / "S01E01.mkv").write_bytes(b"ep1")
        result = _get_adjacent_episode(str(tmp_path / "S01E99.mkv"), +1)
        assert result is None


# ── _make_playlist ──────────────────────────────────────────────────────


class TestMakePlaylist:
    def test_creates_m3u_file(self, tmp_path):
        with patch("server.routers.mpc.state") as mock_state:
            mock_state.ROOT_DIR = tmp_path

            files = [
                r"C:\Media\Show\S01E01.mkv",
                r"C:\Media\Show\S01E02.mkv",
            ]
            result = _make_playlist(files)
            assert result.endswith(".m3u")
            assert Path(result).exists()

            content = Path(result).read_text(encoding="utf-8-sig")
            assert "#EXTM3U" in content
            assert r"C:\Media\Show\S01E01.mkv" in content
            assert r"C:\Media\Show\S01E02.mkv" in content

    def test_creates_parent_directories(self, tmp_path):
        with patch("server.routers.mpc.state") as mock_state:
            mock_state.ROOT_DIR = tmp_path

            # data/ dir doesn't exist yet
            assert not (tmp_path / "data").exists()

            _make_playlist(["/test/file.mkv"])
            assert (tmp_path / "data").exists()
