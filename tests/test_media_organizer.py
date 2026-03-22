"""
Unit tests for server/core/media_organizer.py.

Tests cover:
- _sanitize() illegal character removal
- _pick_video_file() largest-file selection
- MediaOrganizer._destination() path building for movies and TV/anime
- MediaOrganizer.organize() full file-move workflow
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import patch

import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.core.media_organizer import _sanitize, _pick_video_file, MediaOrganizer


# ── Lightweight stand-in for MediaInfo (avoids importing the full client) ──

@dataclass
class FakeMediaInfo:
    title: str = "Test Movie"
    year: Optional[int] = 2024
    tmdb_id: int = 12345
    type: str = "movie"
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_titles: dict = field(default_factory=dict)
    display_name: str = "Test Movie (2024)"


# ── _sanitize ─────────────────────────────────────────────────────────────


class TestSanitize:
    def test_removes_illegal_characters(self):
        assert _sanitize('Test <>"/\\|?* Title') == "Test Title"

    def test_replaces_colon_with_dash(self):
        result = _sanitize("Title: Subtitle")
        assert result == "Title - Subtitle"

    def test_collapses_multiple_spaces(self):
        assert _sanitize("Too   many   spaces") == "Too many spaces"

    def test_strips_leading_trailing_dots_and_spaces(self):
        assert _sanitize("  .Title.  ") == "Title"

    def test_empty_string(self):
        result = _sanitize("")
        assert result == ""

    def test_normal_title_unchanged(self):
        assert _sanitize("The Matrix") == "The Matrix"


# ── _pick_video_file ──────────────────────────────────────────────────────


class TestPickVideoFile:
    def test_picks_largest_video(self, tmp_path):
        small = tmp_path / "small.mkv"
        small.write_bytes(b"x" * 100)
        large = tmp_path / "large.mp4"
        large.write_bytes(b"x" * 5000)
        medium = tmp_path / "medium.avi"
        medium.write_bytes(b"x" * 500)

        result = _pick_video_file(tmp_path)
        assert result == large

    def test_returns_none_for_empty_dir(self, tmp_path):
        assert _pick_video_file(tmp_path) is None

    def test_ignores_non_video_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "image.jpg").write_bytes(b"x" * 1000)
        assert _pick_video_file(tmp_path) is None

    def test_finds_video_in_subdirectory(self, tmp_path):
        sub = tmp_path / "subfolder"
        sub.mkdir()
        video = sub / "episode.mkv"
        video.write_bytes(b"x" * 200)

        result = _pick_video_file(tmp_path)
        assert result == video


# ── MediaOrganizer._destination ───────────────────────────────────────────


class TestMediaOrganizerDestination:
    def test_movie_destination(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(title="Inception", year=2010, tmdb_id=27205, type="movie")
            video = tmp_path / "staging" / "inception.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert "Inception [27205]" in str(dest)
            assert "Inception (2010).mkv" in dest.name

    def test_movie_no_year(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(title="Inception", year=None, tmdb_id=27205, type="movie")
            video = tmp_path / "staging" / "inception.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert dest.name == "Inception.mkv"

    def test_tv_episode_destination(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(
                title="Breaking Bad",
                year=2008,
                tmdb_id=1396,
                type="tv",
                season=1,
                episode=1,
                episode_titles={1: "Pilot"},
            )
            video = tmp_path / "staging" / "ep01.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert "Breaking Bad [1396]" in str(dest)
            assert "S01E01 - Pilot.mkv" in dest.name

    def test_tv_episode_no_title(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(
                title="Show",
                tmdb_id=100,
                type="tv",
                season=2,
                episode=5,
                episode_titles={},
            )
            video = tmp_path / "staging" / "ep05.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert "S02E05.mkv" in dest.name

    def test_tv_season_pack_keeps_original_name(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(
                title="Show",
                tmdb_id=100,
                type="tv",
                season=1,
                episode=None,
            )
            video = tmp_path / "staging" / "Original.Episode.Name.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert "Original.Episode.Name.mkv" in dest.name

    def test_anime_uses_same_logic_as_tv(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(
                title="Attack on Titan",
                tmdb_id=1429,
                type="anime",
                season=1,
                episode=1,
                episode_titles={1: "To You, 2000 Years Later"},
            )
            video = tmp_path / "staging" / "ep01.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert "Attack on Titan [1429]" in str(dest)
            assert "S01E01" in dest.name

    def test_default_season_is_1(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path)
            org = MediaOrganizer()

            media = FakeMediaInfo(
                title="Show",
                tmdb_id=100,
                type="tv",
                season=None,
                episode=3,
                episode_titles={3: "Third"},
            )
            video = tmp_path / "staging" / "ep.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.touch()

            dest = org._destination(video, media)
            assert "S01E03" in dest.name


# ── MediaOrganizer.organize ───────────────────────────────────────────────


class TestMediaOrganizerOrganize:
    def test_organize_single_file(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            org = MediaOrganizer()

            source = tmp_path / "staging" / "movie.mkv"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"fake video data")

            media = FakeMediaInfo(title="Test", year=2024, tmdb_id=999, type="movie")

            result = org.organize(source, media)
            assert result.exists()
            assert "Test [999]" in str(result)
            assert not source.exists()

    def test_organize_directory_picks_largest_video(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            org = MediaOrganizer()

            staging = tmp_path / "staging"
            staging.mkdir(parents=True)
            (staging / "small.mkv").write_bytes(b"x" * 10)
            (staging / "large.mkv").write_bytes(b"x" * 1000)
            (staging / "readme.txt").write_text("info")

            media = FakeMediaInfo(title="Test", year=2024, tmdb_id=999, type="movie")

            result = org.organize(staging, media)
            assert result.exists()
            assert result.stat().st_size == 1000

    def test_organize_directory_no_video_raises(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            org = MediaOrganizer()

            staging = tmp_path / "staging"
            staging.mkdir(parents=True)
            (staging / "readme.txt").write_text("no videos here")

            media = FakeMediaInfo()

            with pytest.raises(FileNotFoundError, match="No video file"):
                org.organize(staging, media)

    def test_organize_creates_parent_dirs(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media" / "deep")
            org = MediaOrganizer()

            source = tmp_path / "staging" / "movie.mkv"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"data")

            media = FakeMediaInfo(title="Test", tmdb_id=1, type="movie")
            result = org.organize(source, media)
            assert result.exists()

    def test_organize_preserves_extension(self, tmp_path):
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            org = MediaOrganizer()

            source = tmp_path / "staging" / "video.mp4"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"data")

            media = FakeMediaInfo(title="Test", year=2024, tmdb_id=1, type="movie")
            result = org.organize(source, media)
            assert result.suffix == ".mp4"

    def test_organize_duplicate_destination_overwrites(self, tmp_path):
        """organize() handles a destination file that already exists (duplicate download)."""
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            org = MediaOrganizer()

            media = FakeMediaInfo(title="Test", year=2024, tmdb_id=999, type="movie")

            # First organize
            source1 = tmp_path / "staging1" / "movie.mkv"
            source1.parent.mkdir(parents=True, exist_ok=True)
            source1.write_bytes(b"first version")
            result1 = org.organize(source1, media)
            assert result1.exists()
            assert result1.read_bytes() == b"first version"

            # Second organize with same media — should overwrite
            source2 = tmp_path / "staging2" / "movie.mkv"
            source2.parent.mkdir(parents=True, exist_ok=True)
            source2.write_bytes(b"second version - longer")
            result2 = org.organize(source2, media)
            assert result2.exists()
            assert result2.read_bytes() == b"second version - longer"

    def test_organize_episode_with_colon_in_title(self, tmp_path):
        """organize() sanitizes colons in episode titles."""
        with patch("server.core.media_organizer.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            org = MediaOrganizer()

            media = FakeMediaInfo(
                title="Show",
                tmdb_id=100,
                type="tv",
                season=1,
                episode=5,
                episode_titles={5: "Part 1: The Beginning"},
            )
            video = tmp_path / "staging" / "ep05.mkv"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"data")

            result = org.organize(video, media)
            assert result.exists()
            assert ":" not in result.name
            assert "S01E05" in result.name
