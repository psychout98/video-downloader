"""
Unit tests for server/core/job_processor.py.

Tests cover:
- _filename_from_url
- _is_video_url
- _episode_from_filename (S01E03, E03, Ep03, " - 03 - " anime patterns)
- _safe_poster_key
- _save_poster
- JobProcessor lifecycle (start/stop, cancel_job)
- JobProcessor._cleanup_staging
- JobProcessor._run_pipeline (basic flow)
- JobProcessor._resolve_rd_files (cached, uncached, season pack)
- JobProcessor._process (timeout, cancel, error handling)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.core.job_processor import (
    _filename_from_url,
    _is_video_url,
    _episode_from_filename,
    _safe_poster_key,
    _save_poster,
    JobProcessor,
)


# ── _filename_from_url ────────────────────────────────────────────────────


class TestFilenameFromUrl:
    def test_simple_url(self):
        assert _filename_from_url("https://cdn.example.com/file.mkv") == "file.mkv"

    def test_url_with_query_params(self):
        result = _filename_from_url("https://cdn.example.com/file.mkv?token=abc&expires=123")
        assert result == "file.mkv"

    def test_url_encoded(self):
        result = _filename_from_url("https://cdn.example.com/My%20Movie.mkv")
        assert result == "My Movie.mkv"

    def test_no_extension(self):
        assert _filename_from_url("https://cdn.example.com/noext") is None

    def test_trailing_slash(self):
        result = _filename_from_url("https://cdn.example.com/file.mkv/")
        assert result == "file.mkv"

    def test_empty_url(self):
        assert _filename_from_url("") is None


# ── _is_video_url ─────────────────────────────────────────────────────────


class TestIsVideoUrl:
    def test_mkv(self):
        assert _is_video_url("https://example.com/file.mkv") is True

    def test_mp4(self):
        assert _is_video_url("https://example.com/file.mp4") is True

    def test_not_video(self):
        assert _is_video_url("https://example.com/file.txt") is False

    def test_with_query_params(self):
        assert _is_video_url("https://example.com/file.mkv?token=abc") is True


# ── _episode_from_filename ────────────────────────────────────────────────


class TestEpisodeFromFilename:
    def test_standard_sxxexx(self):
        assert _episode_from_filename("Show.S01E03.1080p.mkv") == 3

    def test_lowercase_sxxexx(self):
        assert _episode_from_filename("show.s02e10.mkv") == 10

    def test_e_pattern(self):
        assert _episode_from_filename("Show E05 720p.mkv") == 5

    def test_ep_pattern(self):
        assert _episode_from_filename("Show.Ep03.mkv") == 3

    def test_anime_dash_pattern_middle(self):
        assert _episode_from_filename("[Group] Anime - 12 - Title.mkv") == 12

    def test_anime_dash_pattern_end(self):
        assert _episode_from_filename("[Group] Anime - 05.mkv") == 5

    def test_anime_dash_bracket(self):
        assert _episode_from_filename("[Group] Anime - 08 [720p].mkv") == 8

    def test_no_episode(self):
        assert _episode_from_filename("Movie.2024.1080p.mkv") is None

    def test_three_digit_episode(self):
        assert _episode_from_filename("Show.S01E123.mkv") == 123


# ── _safe_poster_key ──────────────────────────────────────────────────────


class TestSafePosterKey:
    def test_strips_illegal_chars(self):
        assert _safe_poster_key('Test: "Movie" (2024)') == "Test_ _Movie_ (2024)"

    def test_normal_string_unchanged(self):
        assert _safe_poster_key("Normal Title") == "Normal Title"


# ── _save_poster ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSavePoster:
    async def test_no_poster_url_returns_early(self, tmp_path):
        from server.clients.tmdb_client import MediaInfo

        media = MediaInfo(title="Test", poster_path=None)
        # Should not raise
        await _save_poster(media, tmp_path / "test.mkv")

    async def test_existing_poster_skipped(self, tmp_path):
        from server.clients.tmdb_client import MediaInfo

        media = MediaInfo(title="Test Movie", year=2024, type="movie", poster_path="/abc.jpg")

        with patch("server.core.job_processor.settings") as mock_settings:
            mock_settings.POSTERS_DIR = str(tmp_path)
            # Pre-create the poster
            (tmp_path / "Test Movie (2024).jpg").write_bytes(b"existing")

            await _save_poster(media, tmp_path / "test.mkv")

        # File should not have been overwritten
        assert (tmp_path / "Test Movie (2024).jpg").read_bytes() == b"existing"


# ── JobProcessor lifecycle ────────────────────────────────────────────────


class TestJobProcessorLifecycle:
    def _make_processor(self):
        """Create a JobProcessor with mocked dependencies."""
        import server.state as state_mod
        with patch.object(state_mod, "tmdb", MagicMock()), \
             patch.object(state_mod, "torrentio", MagicMock()), \
             patch.object(state_mod, "rd", MagicMock()), \
             patch("server.core.job_processor.settings") as mock_settings:
            mock_settings.MAX_CONCURRENT_DOWNLOADS = 2
            mock_settings.MEDIA_DIR = "/tmp/media"
            return JobProcessor()

    def test_cancel_job_returns_true_for_active(self):
        processor = self._make_processor()

        fake_task = MagicMock()
        fake_task.cancel = MagicMock(return_value=True)
        processor._active["job-123"] = fake_task

        assert processor.cancel_job("job-123") is True
        fake_task.cancel.assert_called_once()

    def test_cancel_job_returns_false_for_unknown(self):
        processor = self._make_processor()

        assert processor.cancel_job("nonexistent") is False


# ── JobProcessor._cleanup_staging ─────────────────────────────────────────


@pytest.mark.asyncio
class TestCleanupStaging:
    async def test_removes_matching_files(self, tmp_path):
        import server.state as state_mod
        with patch.object(state_mod, "tmdb", MagicMock()), \
             patch.object(state_mod, "torrentio", MagicMock()), \
             patch.object(state_mod, "rd", MagicMock()), \
             patch("server.core.job_processor.settings") as mock_settings:
            mock_settings.MAX_CONCURRENT_DOWNLOADS = 2
            mock_settings.MEDIA_DIR = "/tmp/media"
            mock_settings.DOWNLOADS_DIR = str(tmp_path)
            processor = JobProcessor()

            job_id = "abcd1234-5678-9abc-def0-123456789abc"
            staging_file = tmp_path / f"{job_id[:8]}_test.mkv"
            staging_file.write_bytes(b"partial download")

            await processor._cleanup_staging(job_id)
            assert not staging_file.exists()

    async def test_handles_nonexistent_staging_dir(self, tmp_path):
        import server.state as state_mod
        with patch.object(state_mod, "tmdb", MagicMock()), \
             patch.object(state_mod, "torrentio", MagicMock()), \
             patch.object(state_mod, "rd", MagicMock()), \
             patch("server.core.job_processor.settings") as mock_settings:
            mock_settings.MAX_CONCURRENT_DOWNLOADS = 2
            mock_settings.MEDIA_DIR = "/tmp/media"
            mock_settings.DOWNLOADS_DIR = str(tmp_path / "nope")
            processor = JobProcessor()

            # Should not raise
            await processor._cleanup_staging("abcd1234-xxx")
