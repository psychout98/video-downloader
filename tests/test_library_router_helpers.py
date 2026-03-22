"""
Unit tests for library router helper functions (server/routers/library.py).

Tests cover:
- _get_episodes_for_item (filesystem scanning, episode parsing, deduplication)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.routers.library import _get_episodes_for_item


# ── _get_episodes_for_item ──────────────────────────────────────────────


class TestGetEpisodesForItem:
    def test_finds_episodes_in_media_dir(self, tmp_path):
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        (show_dir / "S01E01 - Pilot.mkv").write_bytes(b"ep1")
        (show_dir / "S01E02 - Second.mkv").write_bytes(b"ep2")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        assert len(episodes) == 2
        assert episodes[0]["season"] == 1
        assert episodes[0]["episode"] == 1
        assert episodes[0]["title"] == "Pilot"
        assert episodes[0]["rel_path"] == "S01E01 - Pilot.mkv"
        assert episodes[1]["episode"] == 2

    def test_finds_episodes_in_archive_dir(self, tmp_path):
        archive_dir = tmp_path / "archive"
        show_dir = archive_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        (show_dir / "S01E01 - Pilot.mkv").write_bytes(b"ep1")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(archive_dir)

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        assert len(episodes) == 1
        assert episodes[0]["rel_path"] == "S01E01 - Pilot.mkv"

    def test_deduplicates_across_media_and_archive(self, tmp_path):
        media_dir = tmp_path / "media"
        archive_dir = tmp_path / "archive"

        # Same episode in both dirs
        for d in (media_dir, archive_dir):
            show_dir = d / "Show [100]"
            show_dir.mkdir(parents=True)
            (show_dir / "S01E01 - Pilot.mkv").write_bytes(b"ep1")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(archive_dir)

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        # Should only appear once
        assert len(episodes) == 1

    def test_movie_file_returns_single_entry(self, tmp_path):
        media_dir = tmp_path / "media"
        movie_dir = media_dir / "Inception [27205]"
        movie_dir.mkdir(parents=True)
        (movie_dir / "Inception (2010).mkv").write_bytes(b"movie")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Inception [27205]"}
            episodes = _get_episodes_for_item(item)

        assert len(episodes) == 1
        assert episodes[0]["season"] is None
        assert episodes[0]["episode"] is None
        assert episodes[0]["title"] == "Inception (2010)"

    def test_ignores_non_video_files(self, tmp_path):
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        (show_dir / "S01E01 - Pilot.mkv").write_bytes(b"ep1")
        (show_dir / "info.nfo").write_text("metadata")
        (show_dir / "poster.jpg").write_bytes(b"image")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        assert len(episodes) == 1

    def test_empty_folder_returns_empty_list(self, tmp_path):
        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Empty [999]"}
            episodes = _get_episodes_for_item(item)

        assert episodes == []

    def test_sorts_by_season_then_episode(self, tmp_path):
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        (show_dir / "S02E01 - Later.mkv").write_bytes(b"ep")
        (show_dir / "S01E02 - Second.mkv").write_bytes(b"ep")
        (show_dir / "S01E01 - First.mkv").write_bytes(b"ep")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        assert len(episodes) == 3
        assert episodes[0]["episode"] == 1
        assert episodes[0]["season"] == 1
        assert episodes[1]["episode"] == 2
        assert episodes[2]["season"] == 2

    def test_episode_has_default_progress_fields(self, tmp_path):
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        (show_dir / "S01E01 - Pilot.mkv").write_bytes(b"ep1")

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        ep = episodes[0]
        assert ep["progress_pct"] == 0
        assert ep["position_ms"] == 0
        assert ep["duration_ms"] == 0
        assert ep["watched"] is False

    def test_includes_file_size(self, tmp_path):
        media_dir = tmp_path / "media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        (show_dir / "S01E01.mkv").write_bytes(b"x" * 5000)

        with patch("server.routers.library.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")

            item = {"folder_name": "Show [100]"}
            episodes = _get_episodes_for_item(item)

        assert episodes[0]["size_bytes"] == 5000
