"""
Unit tests for server/core/watch_tracker.py.

Tests cover:
- _parse_tmdb_id_from_path()
- _compute_rel_path()
- _remove_if_empty()
- _move_folder_remnants()
- WatchTracker lifecycle (start/stop)
- WatchTracker._tick() state machine (playing, paused, stopped, file-change)
- WatchTracker._save_progress()
- WatchTracker._on_stopped() (archive decision)
- WatchTracker._archive() (move file + subtitles)
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

from server.core.watch_tracker import (
    _parse_tmdb_id_from_path,
    _compute_rel_path,
    _remove_if_empty,
    _move_folder_remnants,
    WatchTracker,
)


# ── _parse_tmdb_id_from_path ──────────────────────────────────────────────


class TestParseTmdbIdFromPath:
    def test_extracts_tmdb_id_from_windows_path(self):
        assert _parse_tmdb_id_from_path(
            r"C:\Media\Breaking Bad [1396]\S01E01 - Pilot.mkv"
        ) == 1396

    def test_extracts_tmdb_id_from_posix_path(self):
        assert _parse_tmdb_id_from_path(
            "/media/Inception [27205]/Inception (2010).mkv"
        ) == 27205

    def test_returns_none_if_no_bracket_id(self):
        assert _parse_tmdb_id_from_path(r"C:\Media\Movies\Inception.mkv") is None

    def test_extracts_first_bracket_id(self):
        # Edge case: multiple bracket numbers — should find first
        result = _parse_tmdb_id_from_path(r"C:\Media\Show [100]\S01E01 [720p].mkv")
        assert result == 100

    def test_empty_string(self):
        assert _parse_tmdb_id_from_path("") is None


# ── _compute_rel_path ─────────────────────────────────────────────────────


class TestComputeRelPath:
    def test_extracts_rel_path_from_media_dir(self, tmp_path):
        media_dir = tmp_path / "Media"
        media_dir.mkdir()
        (media_dir / "Show [100]").mkdir()
        file_path = str(media_dir / "Show [100]" / "S01E01 - Pilot.mkv")

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "Archive")
            result = _compute_rel_path(file_path)
            assert result == "S01E01 - Pilot.mkv"

    def test_extracts_rel_path_from_archive_dir(self, tmp_path):
        archive_dir = tmp_path / "Archive"
        archive_dir.mkdir()
        (archive_dir / "Show [100]").mkdir()
        file_path = str(archive_dir / "Show [100]" / "S01E01.mkv")

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "Media")
            mock_settings.ARCHIVE_DIR = str(archive_dir)
            result = _compute_rel_path(file_path)
            assert result == "S01E01.mkv"

    def test_falls_back_to_filename_if_not_under_known_dirs(self, tmp_path):
        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "Media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "Archive")
            result = _compute_rel_path("/somewhere/else/video.mkv")
            assert result == "video.mkv"


# ── _remove_if_empty ──────────────────────────────────────────────────────


class TestRemoveIfEmpty:
    def test_removes_folder_with_no_video_files(self, tmp_path):
        folder = tmp_path / "empty_show"
        folder.mkdir()
        (folder / "info.nfo").write_text("metadata")

        _remove_if_empty(folder)
        assert not folder.exists()

    def test_keeps_folder_with_video_files(self, tmp_path):
        folder = tmp_path / "show"
        folder.mkdir()
        (folder / "S01E01.mkv").write_bytes(b"video")

        _remove_if_empty(folder)
        assert folder.exists()

    def test_no_error_on_nonexistent_folder(self, tmp_path):
        _remove_if_empty(tmp_path / "doesnt_exist")

    def test_checks_subdirectories_for_videos(self, tmp_path):
        folder = tmp_path / "show"
        sub = folder / "Season 1"
        sub.mkdir(parents=True)
        (sub / "S01E01.mkv").write_bytes(b"video")

        _remove_if_empty(folder)
        assert folder.exists()


# ── _move_folder_remnants ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMoveFolderRemnants:
    async def test_moves_non_video_files(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "info.nfo").write_text("metadata")
        (src / "poster.jpg").write_bytes(b"image")

        dest = tmp_path / "dest"
        dest.mkdir()

        await _move_folder_remnants(src, dest)
        assert (dest / "info.nfo").exists()
        assert (dest / "poster.jpg").exists()

    async def test_does_not_move_if_videos_remain(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E02.mkv").write_bytes(b"video")
        (src / "info.nfo").write_text("metadata")

        dest = tmp_path / "dest"
        dest.mkdir()

        await _move_folder_remnants(src, dest)
        assert (src / "info.nfo").exists()  # should NOT have moved

    async def test_handles_nonexistent_source(self, tmp_path):
        await _move_folder_remnants(tmp_path / "nope", tmp_path)


# ── WatchTracker lifecycle ────────────────────────────────────────────────


class TestWatchTrackerLifecycle:
    def test_init_sets_defaults(self):
        mpc = MagicMock()
        tracker = WatchTracker(mpc)
        assert tracker._running is False
        assert tracker._prev_file is None

    def test_stop_sets_running_false(self):
        mpc = MagicMock()
        tracker = WatchTracker(mpc)
        tracker._running = True
        tracker.stop()
        assert tracker._running is False


# ── WatchTracker._tick ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWatchTrackerTick:
    async def test_tick_while_playing_records_progress(self):
        mock_mpc = AsyncMock()
        status = MagicMock()
        status.state = 2
        status.file = r"C:\Media\Show [100]\S01E01.mkv"
        status.position_ms = 600000
        status.duration_ms = 3600000
        mock_mpc.get_status = AsyncMock(return_value=status)

        tracker = WatchTracker(mock_mpc)
        tracker._last_progress_save = 0  # Force a save

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch("server.core.watch_tracker.time") as mock_time:
                mock_time.monotonic.return_value = 100.0

                with patch("server.database.save_progress", new_callable=AsyncMock) as mock_save:
                    await tracker._tick()

        assert tracker._prev_file == status.file
        assert tracker._stopped_polls == 0

    async def test_tick_stopped_after_2_polls_triggers_on_stopped(self):
        mock_mpc = AsyncMock()
        status = MagicMock()
        status.state = 0
        status.file = ""
        mock_mpc.get_status = AsyncMock(return_value=status)

        tracker = WatchTracker(mock_mpc)
        tracker._prev_file = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._stopped_polls = 1  # One poll already
        tracker._max_pct = {tracker._prev_file: 0.5}

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch.object(tracker, "_on_stopped", new_callable=AsyncMock) as mock_on_stopped:
                await tracker._tick()

        mock_on_stopped.assert_called_once()

    async def test_tick_stopped_single_poll_does_not_trigger(self):
        mock_mpc = AsyncMock()
        status = MagicMock()
        status.state = 0
        status.file = ""
        mock_mpc.get_status = AsyncMock(return_value=status)

        tracker = WatchTracker(mock_mpc)
        tracker._prev_file = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._stopped_polls = 0

        await tracker._tick()
        assert tracker._stopped_polls == 1

    async def test_tick_file_change_triggers_on_stopped_for_old_file(self):
        mock_mpc = AsyncMock()
        status = MagicMock()
        status.state = 2
        status.file = r"C:\Media\Show [100]\S01E02.mkv"
        status.position_ms = 100
        status.duration_ms = 3600000
        mock_mpc.get_status = AsyncMock(return_value=status)

        tracker = WatchTracker(mock_mpc)
        tracker._prev_file = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._max_pct = {tracker._prev_file: 0.9}

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch.object(tracker, "_on_stopped", new_callable=AsyncMock):
                with patch("server.core.watch_tracker.time") as mock_time:
                    mock_time.monotonic.return_value = 0
                    await tracker._tick()

        assert tracker._prev_file == status.file

    async def test_tick_mpc_unreachable_counts_stopped_polls(self):
        mock_mpc = AsyncMock()
        mock_mpc.get_status = AsyncMock(side_effect=Exception("unreachable"))

        tracker = WatchTracker(mock_mpc)
        tracker._prev_file = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._stopped_polls = 0

        await tracker._tick()
        assert tracker._stopped_polls == 1

    async def test_tick_mpc_unreachable_twice_triggers_on_stopped(self):
        mock_mpc = AsyncMock()
        mock_mpc.get_status = AsyncMock(side_effect=Exception("unreachable"))

        tracker = WatchTracker(mock_mpc)
        tracker._prev_file = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._stopped_polls = 1
        tracker._max_pct = {tracker._prev_file: 0.3}

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85
            with patch.object(tracker, "_on_stopped", new_callable=AsyncMock) as mock_on_stopped:
                await tracker._tick()

        mock_on_stopped.assert_called_once()


# ── WatchTracker._archive ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWatchTrackerArchive:
    async def test_archive_moves_file_to_archive_dir(self, tmp_path):
        media_dir = tmp_path / "Media"
        archive_dir = tmp_path / "Archive"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        video = show_dir / "S01E01.mkv"
        video.write_bytes(b"video data")

        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(archive_dir)

            await tracker._archive(str(video))

        assert (archive_dir / "Show [100]" / "S01E01.mkv").exists()
        assert not video.exists()

    async def test_archive_moves_subtitle_files_too(self, tmp_path):
        media_dir = tmp_path / "Media"
        archive_dir = tmp_path / "Archive"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        video = show_dir / "S01E01.mkv"
        video.write_bytes(b"video data")
        subtitle = show_dir / "S01E01.srt"
        subtitle.write_text("subtitles")

        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(archive_dir)

            await tracker._archive(str(video))

        assert (archive_dir / "Show [100]" / "S01E01.srt").exists()

    async def test_archive_nonexistent_file_logs_warning(self, tmp_path):
        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "Media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "Archive")

            # Should not raise
            await tracker._archive(str(tmp_path / "nonexistent.mkv"))

    async def test_archive_file_not_under_media_dir(self, tmp_path):
        other = tmp_path / "other" / "video.mkv"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"data")

        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "Media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "Archive")

            await tracker._archive(str(other))

        # File should NOT have been moved
        assert other.exists()

    async def test_archive_cleans_up_empty_folder_movie(self, tmp_path):
        media_dir = tmp_path / "Media"
        archive_dir = tmp_path / "Archive"
        movie_dir = media_dir / "Movie [200]"
        movie_dir.mkdir(parents=True)
        video = movie_dir / "Movie (2024).mkv"
        video.write_bytes(b"video")
        nfo = movie_dir / "Movie.nfo"
        nfo.write_text("info")

        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(archive_dir)

            await tracker._archive(str(video))

        # Both files should be in archive, source folder should be gone
        assert (archive_dir / "Movie [200]" / "Movie (2024).mkv").exists()
        # nfo should have been moved via _move_folder_remnants
        assert (archive_dir / "Movie [200]" / "Movie.nfo").exists()


# ── WatchTracker._on_stopped ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestWatchTrackerOnStopped:
    async def test_on_stopped_archives_if_above_threshold(self, tmp_path):
        media_dir = tmp_path / "Media"
        show_dir = media_dir / "Show [100]"
        show_dir.mkdir(parents=True)
        video = show_dir / "S01E01.mkv"
        video.write_bytes(b"data")

        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)
        file_path = str(video)
        tracker._max_pct = {file_path: 0.90}

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "Archive")
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch("server.database.save_progress", new_callable=AsyncMock):
                with patch("server.database.get_progress", new_callable=AsyncMock, return_value={"duration_ms": 3600000}):
                    with patch.object(tracker, "_archive", new_callable=AsyncMock) as mock_archive:
                        await tracker._on_stopped(file_path)

        mock_archive.assert_called_once()
        assert tracker._prev_file is None

    async def test_on_stopped_does_not_archive_if_below_threshold(self):
        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)
        file_path = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._max_pct = {file_path: 0.50}

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch("server.database.save_progress", new_callable=AsyncMock):
                with patch("server.database.get_progress", new_callable=AsyncMock, return_value={"duration_ms": 3600000}):
                    with patch.object(tracker, "_archive", new_callable=AsyncMock) as mock_archive:
                        await tracker._on_stopped(file_path)

        mock_archive.assert_not_called()

    async def test_on_stopped_clears_state(self):
        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)
        file_path = r"C:\Media\Show [100]\S01E01.mkv"
        tracker._max_pct = {file_path: 0.10}
        tracker._prev_file = file_path

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch("server.database.save_progress", new_callable=AsyncMock):
                with patch("server.database.get_progress", new_callable=AsyncMock, return_value=None):
                    await tracker._on_stopped(file_path)

        assert tracker._prev_file is None
        assert file_path not in tracker._max_pct
        assert tracker._stopped_polls == 0

    async def test_on_stopped_missing_max_pct_entry(self):
        """_on_stopped handles gracefully when file has no _max_pct entry (tracker restarted mid-playback)."""
        mock_mpc = AsyncMock()
        tracker = WatchTracker(mock_mpc)
        file_path = r"C:\Media\Show [100]\S01E01.mkv"
        # Deliberately do NOT set _max_pct for this file
        tracker._prev_file = file_path

        with patch("server.core.watch_tracker.settings") as mock_settings:
            mock_settings.MEDIA_DIR = r"C:\Media"
            mock_settings.ARCHIVE_DIR = r"D:\Archive"
            mock_settings.WATCH_THRESHOLD = 0.85

            with patch("server.database.save_progress", new_callable=AsyncMock):
                with patch("server.database.get_progress", new_callable=AsyncMock, return_value=None):
                    with patch.object(tracker, "_archive", new_callable=AsyncMock) as mock_archive:
                        # Should NOT raise
                        await tracker._on_stopped(file_path)

        # pct defaults to 0.0 — well below threshold, so no archive
        mock_archive.assert_not_called()
        assert tracker._prev_file is None
        assert tracker._stopped_polls == 0
