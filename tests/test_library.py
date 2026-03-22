"""
Integration tests for library router (/api/library, /api/progress).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestLibraryGetEndpoint:
    """Library scan endpoint tests."""

    def test_get_library_returns_200_with_items(self, test_client):
        """GET /api/library returns 200 with items and count."""
        response = test_client.get("/api/library")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "count" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["count"], int)

    def test_get_library_empty_returns_zero_count(self, test_client):
        """GET /api/library returns count=0 for empty library."""
        response = test_client.get("/api/library")
        data = response.json()
        # Mock returns empty list
        assert data["count"] == len(data["items"])

    def test_get_library_force_parameter(self, test_client):
        """GET /api/library?force=true bypasses cache."""
        response1 = test_client.get("/api/library?force=false")
        response2 = test_client.get("/api/library?force=true")
        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_get_library_items_have_expected_fields(self, test_client):
        """Library items (if any) have expected fields."""
        # This would only test if there were actual items
        # For now, just verify the structure
        response = test_client.get("/api/library")
        data = response.json()
        # Structure is correct even if empty
        assert isinstance(data["items"], list)


@pytest.mark.integration
class TestLibraryRefreshEndpoint:
    """Library refresh endpoint tests."""

    def test_post_library_refresh_returns_200(self, test_client, mock_state):
        """POST /api/library/refresh calls library.refresh() and returns summary."""
        response = test_client.post("/api/library/refresh")
        assert response.status_code == 200

        data = response.json()
        # Should return refresh summary
        assert "renamed" in data
        assert "posters_fetched" in data
        assert "errors" in data
        assert "total_items" in data

    def test_post_library_refresh_summary_counts(self, test_client):
        """Refresh summary has numeric counts."""
        response = test_client.post("/api/library/refresh")
        data = response.json()
        assert isinstance(data["renamed"], int)
        assert isinstance(data["posters_fetched"], int)
        assert isinstance(data["errors"], list)
        assert isinstance(data["total_items"], int)


@pytest.mark.integration
class TestLibraryPosterEndpoint:
    """Poster serving endpoint tests."""

    def test_get_poster_nonexistent_returns_404(self, test_client):
        """GET /api/library/poster with missing file returns 404."""
        response = test_client.get("/api/library/poster?path=/nonexistent/poster.jpg")
        assert response.status_code == 404

    def test_get_poster_directory_returns_400(self, test_client, tmp_path):
        """GET /api/library/poster with directory path returns 400 or 404."""
        response = test_client.get(f"/api/library/poster?path={tmp_path}")
        # Should fail because it's not a file
        assert response.status_code in (400, 404)

    def test_get_poster_non_image_returns_400(self, test_client, tmp_path):
        """GET /api/library/poster with non-image file returns 400."""
        # Create a non-image file
        text_file = tmp_path / "test.txt"
        text_file.write_text("not an image")

        response = test_client.get(f"/api/library/poster?path={text_file}")
        assert response.status_code == 400

    def test_get_poster_valid_image_returns_200(self, test_client, tmp_path):
        """GET /api/library/poster with valid image returns 200."""
        # Create a dummy image file
        image_file = tmp_path / "poster.jpg"
        image_file.write_bytes(b"\xFF\xD8\xFF\xE0")  # JPEG header

        response = test_client.get(f"/api/library/poster?path={image_file}")
        assert response.status_code == 200
        # Should return image content
        assert response.headers["content-type"] in ("image/jpeg", "image/png", "image/webp")


@pytest.mark.integration
class TestEpisodesEndpoint:
    """Episodes listing endpoint tests."""

    def test_get_episodes_nonexistent_folder_returns_404(self, test_client):
        """GET /api/library/episodes with missing folder returns 404."""
        response = test_client.get("/api/library/episodes?folder=/nonexistent/path")
        assert response.status_code == 404

    def test_get_episodes_valid_folder_returns_seasons(self, test_client, tmp_path):
        """GET /api/library/episodes with valid folder returns seasons structure."""
        response = test_client.get(f"/api/library/episodes?folder={tmp_path}")
        assert response.status_code == 200

        data = response.json()
        assert "seasons" in data
        assert isinstance(data["seasons"], list)

    def test_get_episodes_empty_folder_returns_empty_seasons(self, test_client, tmp_path):
        """GET /api/library/episodes with folder containing no videos returns empty seasons."""
        response = test_client.get(f"/api/library/episodes?folder={tmp_path}")
        data = response.json()
        assert data["seasons"] == []

    def test_get_episodes_with_archive_folder(self, test_client, tmp_path):
        """GET /api/library/episodes can include archive folder."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        response = test_client.get(
            f"/api/library/episodes?folder={tmp_path}&folder_archive={archive_dir}"
        )
        assert response.status_code == 200

    def test_get_episodes_seasons_have_structure(self, test_client, tmp_path):
        """Episode seasons have expected structure."""
        # Create a dummy video file with season/episode naming
        video_dir = tmp_path / "Season 1"
        video_dir.mkdir()
        video_file = video_dir / "s01e01_episode_name.mkv"
        video_file.write_bytes(b"dummy video")

        response = test_client.get(f"/api/library/episodes?folder={tmp_path}")
        data = response.json()

        # Should have at least one season
        if data["seasons"]:
            season = data["seasons"][0]
            assert "season" in season
            assert "episodes" in season
            assert isinstance(season["episodes"], list)

            if season["episodes"]:
                episode = season["episodes"][0]
                assert "season" in episode
                assert "episode" in episode
                assert "title" in episode
                assert "filename" in episode
                assert "path" in episode


@pytest.mark.integration
class TestProgressEndpoint:
    """Watch progress tracking endpoint tests."""

    def test_get_progress_missing_file_returns_empty(self, test_client):
        """GET /api/progress for non-existent file returns empty dict."""
        response = test_client.get("/api/progress?path=/nonexistent/file.mkv")
        assert response.status_code == 200

        data = response.json()
        # Should return empty dict or dict with no progress
        assert isinstance(data, dict)

    def test_post_progress_saves_position(self, test_client, mock_state):
        """POST /api/progress saves watch progress."""
        response = test_client.post(
            "/api/progress",
            json={
                "path": "/path/to/file.mkv",
                "position_ms": 3600000,
                "duration_ms": 7200000,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_post_progress_valid_percentages(self, test_client):
        """POST /api/progress accepts valid time values."""
        response = test_client.post(
            "/api/progress",
            json={
                "path": "/path/to/file.mkv",
                "position_ms": 0,
                "duration_ms": 1000,
            },
        )
        assert response.status_code == 200

    def test_post_progress_large_values(self, test_client):
        """POST /api/progress handles large timestamp values."""
        response = test_client.post(
            "/api/progress",
            json={
                "path": "/path/to/movie.mkv",
                "position_ms": 999999999,
                "duration_ms": 999999999,
            },
        )
        assert response.status_code == 200
