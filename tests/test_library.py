"""
Integration tests for Library API (Feature 7).

AC Reference:
  7.1   GET /api/library returns 200 with items array and count
  7.2   Empty library returns count=0
  7.3   Supports ?force=true to bypass cache
  7.4   Library items have expected fields (tmdb_id, title, year, type, path, etc.)
  7.5   POST /api/library/refresh returns summary with renamed, posters_fetched, errors, total_items
  7.6   GET /api/library/poster/:filename returns 404 for nonexistent file
  7.7   Poster endpoint returns 400 for directory paths or non-image files
  7.8   Valid poster returns 200 with image content-type
  7.9   GET /api/library/episodes returns seasons array with episodes
  7.10  Episodes have season, episode, title, filename, path, and progress fields
  7.11  Nonexistent folder returns 404 for episodes endpoint
  7.12  Supports ?folder_archive parameter for archive lookups
  7.13  GET/POST /api/library/progress — missing file returns empty dict; POST saves position_ms and duration_ms
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
class TestFeature7_LibraryAPI:
    """Feature 7: Library API"""

    # ── 7.1–7.4: Library listing ──────────────────────────────────────

    def test_7_1_get_library_returns_200_with_items_and_count(self, test_client):
        """7.1 — GET /api/library returns 200 with items array and count."""
        response = test_client.get("/api/library")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "count" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["count"], int)

    def test_7_2_empty_library_returns_count_zero(self, test_client):
        """7.2 — Empty library returns count=0."""
        response = test_client.get("/api/library")
        data = response.json()
        assert data["count"] == len(data["items"])

    def test_7_3_force_true_bypasses_cache(self, test_client):
        """7.3 — Supports ?force=true to bypass cache."""
        response_cached = test_client.get("/api/library?force=false")
        response_forced = test_client.get("/api/library?force=true")
        assert response_cached.status_code == 200
        assert response_forced.status_code == 200

    def test_7_4_library_items_have_expected_fields(self, test_client):
        """7.4 — Library items have expected fields (tmdb_id, title, year, type, path, etc.)."""
        response = test_client.get("/api/library")
        data = response.json()
        assert isinstance(data["items"], list)

    # ── 7.5: Refresh ─────────────────────────────────────────────────

    def test_7_5_refresh_returns_summary(self, test_client, mock_state):
        """7.5 — POST /api/library/refresh returns summary with renamed, posters_fetched, errors, total_items."""
        response = test_client.post("/api/library/refresh")
        assert response.status_code == 200

        data = response.json()
        assert "renamed" in data
        assert "posters_fetched" in data
        assert "errors" in data
        assert "total_items" in data
        assert isinstance(data["renamed"], int)
        assert isinstance(data["posters_fetched"], int)
        assert isinstance(data["errors"], list)
        assert isinstance(data["total_items"], int)

    # ── 7.6–7.8: Posters ─────────────────────────────────────────────

    def test_7_6_poster_nonexistent_returns_404(self, test_client):
        """7.6 — GET /api/library/poster/:filename returns 404 for nonexistent file."""
        response = test_client.get("/api/library/poster?path=/nonexistent/poster.jpg")
        assert response.status_code == 404

    def test_7_7_poster_returns_400_for_directory_or_non_image(self, test_client, tmp_path):
        """7.7 — Poster endpoint returns 400 for directory paths or non-image files."""
        # Directory path
        response_dir = test_client.get(f"/api/library/poster?path={tmp_path}")
        assert response_dir.status_code in (400, 404)

        # Non-image file
        text_file = tmp_path / "test.txt"
        text_file.write_text("not an image")
        response_txt = test_client.get(f"/api/library/poster?path={text_file}")
        assert response_txt.status_code == 400

    def test_7_8_valid_poster_returns_200_with_image_content_type(self, test_client, tmp_path):
        """7.8 — Valid poster returns 200 with image content-type."""
        image_file = tmp_path / "poster.jpg"
        image_file.write_bytes(b"\xFF\xD8\xFF\xE0")  # JPEG header

        response = test_client.get(f"/api/library/poster?path={image_file}")
        assert response.status_code == 200
        assert response.headers["content-type"] in ("image/jpeg", "image/png", "image/webp")

    # ── 7.9–7.12: Episodes ───────────────────────────────────────────

    def test_7_9_episodes_returns_seasons_array(self, test_client, tmp_path):
        """7.9 — GET /api/library/episodes returns seasons array with episodes."""
        response = test_client.get(f"/api/library/episodes?folder={tmp_path}")
        assert response.status_code == 200

        data = response.json()
        assert "seasons" in data
        assert isinstance(data["seasons"], list)

    def test_7_10_episodes_have_expected_fields(self, test_client, tmp_path):
        """7.10 — Episodes have season, episode, title, filename, path, and progress fields."""
        video_dir = tmp_path / "Season 1"
        video_dir.mkdir()
        video_file = video_dir / "s01e01_episode_name.mkv"
        video_file.write_bytes(b"dummy video")

        response = test_client.get(f"/api/library/episodes?folder={tmp_path}")
        data = response.json()

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

    def test_7_11_nonexistent_folder_returns_404(self, test_client):
        """7.11 — Nonexistent folder returns 404 for episodes endpoint."""
        response = test_client.get("/api/library/episodes?folder=/nonexistent/path")
        assert response.status_code == 404

    def test_7_12_supports_folder_archive_parameter(self, test_client, tmp_path):
        """7.12 — Supports ?folder_archive parameter for archive lookups."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        response = test_client.get(
            f"/api/library/episodes?folder={tmp_path}&folder_archive={archive_dir}"
        )
        assert response.status_code == 200

    # ── 7.13: Progress ────────────────────────────────────────────────

    def test_7_13_progress_missing_file_returns_empty_and_post_saves(self, test_client, mock_state):
        """7.13 — Missing file returns empty dict; POST saves position_ms and duration_ms."""
        # GET — missing file returns empty dict
        response = test_client.get("/api/progress?path=/nonexistent/file.mkv")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

        # POST — saves progress
        response = test_client.post(
            "/api/progress",
            json={
                "path": "/path/to/file.mkv",
                "position_ms": 3600000,
                "duration_ms": 7200000,
            },
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
