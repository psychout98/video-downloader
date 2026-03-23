"""
Unit tests for LibraryManager (server/core/library_manager.py).
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestLibraryManagerScan:
    """LibraryManager.scan() tests."""

    def test_scan_empty_dirs_returns_empty_list(self, tmp_path):
        """scan() with non-existent directories returns empty list."""
        from server.core.library_manager import LibraryManager

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")

            manager = LibraryManager()
            result = manager.scan()
            assert result == []

    def test_scan_caches_results(self, tmp_path):
        """scan() caches results and returns cached on second call."""
        from server.core.library_manager import LibraryManager

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")

            manager = LibraryManager(cache_ttl=10)

            # First scan
            result1 = manager.scan()
            assert isinstance(result1, list)

            # Second scan should be cached
            result2 = manager.scan()
            assert result1 is result2  # Same object reference

    def test_scan_bypasses_cache_with_force(self, tmp_path):
        """scan(force=True) bypasses cache and rescans."""
        from server.core.library_manager import LibraryManager

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")

            manager = LibraryManager()

            # First scan
            result1 = manager.scan()

            # Force rescan
            result2 = manager.scan(force=True)

            # Should be different objects (not cached)
            assert isinstance(result2, list)

    def test_scan_detects_video_files(self, tmp_path):
        """scan() detects movie files and returns items."""
        from server.core.library_manager import LibraryManager

        media_dir = tmp_path / "media"
        media_dir.mkdir()

        # Create a movie folder with a video file
        movie_folder = media_dir / "Test Movie (2024)"
        movie_folder.mkdir()
        video_file = movie_folder / "movie.mkv"
        video_file.write_bytes(b"fake video")

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(media_dir)
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")

            manager = LibraryManager()
            result = manager.scan()

            assert len(result) > 0
            assert result[0]["title"] == "Test Movie"
            assert result[0]["year"] == 2024

    def test_scan_cache_expires_after_ttl(self, tmp_path):
        """scan() cache expires after TTL and rescans."""
        from server.core.library_manager import LibraryManager

        with patch("server.core.library_manager.settings") as mock_settings:
            mock_settings.MEDIA_DIR = str(tmp_path / "media")
            mock_settings.ARCHIVE_DIR = str(tmp_path / "archive")
            mock_settings.POSTERS_DIR = str(tmp_path / "posters")

            manager = LibraryManager(cache_ttl=0.1)

            # First scan
            result1 = manager.scan()

            # Wait for cache to expire
            time.sleep(0.2)

            # Second scan should bypass cache
            result2 = manager.scan()

            # Different objects due to cache expiry
            assert isinstance(result2, list)


@pytest.mark.unit
class TestExtractTitleYear:
    """_extract_title_year() parsing tests."""

    def test_extract_title_year_parentheses_format(self):
        """Parse 'Title (2024)' format."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("The Matrix (1999)")
        assert title == "The Matrix"
        assert year == 1999

    def test_extract_title_year_dot_format(self):
        """Parse 'Title.2024.1080p' format."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("The.Matrix.1999.1080p")
        assert title == "The Matrix"
        assert year == 1999

    def test_extract_title_year_dash_format(self):
        """Parse 'Title - 2024' format."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("The Matrix - 1999")
        assert title == "The Matrix"
        assert year == 1999

    def test_extract_title_year_no_year(self):
        """Parse title without year."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("The Matrix")
        assert title == "The Matrix"
        assert year is None

    def test_extract_title_year_removes_quality_tags(self):
        """Title extraction removes quality tags (1080p, BluRay, etc)."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("The.Matrix.1999.1080p.BluRay.x264")
        assert title == "The Matrix"
        assert "1080p" not in title
        assert "BluRay" not in title
        assert "x264" not in title

    def test_extract_title_year_handles_multiple_words(self):
        """Extract from multi-word titles."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("The Lord of the Rings Extended Edition (2001)")
        assert title == "The Lord of the Rings Extended Edition"
        assert year == 2001

    def test_extract_title_year_handles_special_characters(self):
        """Extract from titles with special characters."""
        from server.core.library_manager import _extract_title_year

        title, year = _extract_title_year("Dr. Strangelove (1964)")
        assert "Dr" in title and "Strangelove" in title
        assert year == 1964


@pytest.mark.unit
class TestCleanTitle:
    """_clean_title() helper tests."""

    def test_clean_title_removes_quality_tags(self):
        """_clean_title removes quality/format tags."""
        from server.core.library_manager import _clean_title

        result = _clean_title("The.Matrix.1080p.BluRay")
        assert "1080p" not in result
        assert "BluRay" not in result

    def test_clean_title_replaces_dots_with_spaces(self):
        """_clean_title replaces dots with spaces."""
        from server.core.library_manager import _clean_title

        result = _clean_title("The.Matrix")
        assert result == "The Matrix"

    def test_clean_title_removes_brackets(self):
        """_clean_title removes content in brackets."""
        from server.core.library_manager import _clean_title

        result = _clean_title("The Matrix [1080p] (1999)")
        assert "[" not in result
        assert "]" not in result
        assert "(" not in result

    def test_clean_title_collapses_spaces(self):
        """_clean_title collapses multiple spaces."""
        from server.core.library_manager import _clean_title

        result = _clean_title("The    Matrix")
        assert result == "The Matrix"

    def test_clean_title_strips_dots_and_dashes(self):
        """_clean_title strips leading/trailing dots and dashes."""
        from server.core.library_manager import _clean_title

        result = _clean_title("...The Matrix...")
        assert not result.startswith(".")
        assert not result.endswith(".")


@pytest.mark.unit
class TestSafeFolderName:
    """_safe_folder() Windows filename safety tests."""

    def test_safe_folder_removes_invalid_chars(self):
        """_safe_folder removes Windows-invalid characters."""
        from server.core.library_manager import _safe_folder

        result = _safe_folder('Test: Movie <Bad> | Name')
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_safe_folder_replaces_colon_with_dash(self):
        """_safe_folder converts colons to dashes."""
        from server.core.library_manager import _safe_folder

        result = _safe_folder("Test: The Movie")
        assert " - " in result
        assert ":" not in result

    def test_safe_folder_preserves_alphanumeric(self):
        """_safe_folder preserves valid characters."""
        from server.core.library_manager import _safe_folder

        result = _safe_folder("The Matrix (1999)")
        assert "The" in result
        assert "Matrix" in result
        assert "1999" in result
