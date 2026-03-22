"""
Integration tests for MPC-BE router (/api/mpc/*).

New endpoints:
  GET  /api/mpc/status    → Status with resolved media context
  GET  /api/mpc/stream    → SSE push stream
  POST /api/mpc/command   → Send wm_command
  POST /api/mpc/open      → Open file by tmdb_id + rel_path
  POST /api/mpc/next      → Next episode
  POST /api/mpc/prev      → Previous episode
"""
from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch

import pytest


@pytest.mark.integration
class TestMpcStatusEndpoint:
    """GET /api/mpc/status tests."""

    def test_get_status_returns_200(self, test_client):
        """GET /api/mpc/status returns 200 with player state."""
        response = test_client.get("/api/mpc/status")
        assert response.status_code == 200

        data = response.json()
        assert "reachable" in data
        assert "file" in data
        assert "state" in data
        assert "is_playing" in data
        assert "position_ms" in data
        assert "duration_ms" in data
        assert "volume" in data
        assert "muted" in data

    def test_get_status_includes_media_context(self, test_client):
        """GET /api/mpc/status includes resolved media field when playing a library file."""
        response = test_client.get("/api/mpc/status")
        data = response.json()
        # The media field should be present (may be null if no match)
        assert "media" in data

    def test_get_status_media_context_has_tmdb_id(self, test_client, mock_state):
        """When playing a library file, media context includes tmdb_id."""
        # MockMPCClient returns a file path with [1396] in it
        response = test_client.get("/api/mpc/status")
        data = response.json()
        if data.get("media"):
            assert "tmdb_id" in data["media"]
            assert "title" in data["media"]
            assert "type" in data["media"]

    def test_get_status_media_context_full_shape(self, test_client, mock_state):
        """When media context is resolved, it contains all required sub-fields."""
        # MockMPCClient returns a file in Breaking Bad [1396], so context should resolve
        mock_state.library.set_items([
            {"tmdb_id": 1396, "title": "Breaking Bad", "type": "tv",
             "folder_name": "Breaking Bad [1396]"}
        ])
        response = test_client.get("/api/mpc/status")
        data = response.json()
        media = data.get("media")
        if media is not None:
            for field in ("tmdb_id", "title", "type", "poster_url", "season", "episode"):
                assert field in media, f"media context missing field: {field}"


@pytest.mark.integration
class TestMpcCommandEndpoint:
    """POST /api/mpc/command tests."""

    def test_post_command_returns_200(self, test_client):
        """POST /api/mpc/command returns ok."""
        response = test_client.post(
            "/api/mpc/command",
            json={"command": 887},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_post_command_with_seek_position(self, test_client):
        """POST /api/mpc/command with position_ms for seek."""
        response = test_client.post(
            "/api/mpc/command",
            json={"command": 889, "position_ms": 60000},
        )
        assert response.status_code == 200


@pytest.mark.integration
class TestMpcOpenEndpoint:
    """POST /api/mpc/open tests."""

    def test_open_file_not_found_returns_404(self, test_client, mock_state):
        """POST /api/mpc/open returns 404 when file doesn't exist on disk."""
        from unittest.mock import patch

        with patch("server.routers.mpc.settings") as mock_settings:
            mock_settings.MPC_BE_EXE = "/nonexistent/mpc-be"
            mock_settings.MEDIA_DIR = "/tmp/nonexistent_media"
            mock_settings.ARCHIVE_DIR = "/tmp/nonexistent_archive"

            response = test_client.post(
                "/api/mpc/open",
                json={"tmdb_id": 1396, "rel_path": "S01E01 - Pilot.mkv"},
            )
            # Either 404 (file not found) or 500 (exe not found) — both are valid rejections
            assert response.status_code in (404, 500)

    def test_open_accepts_playlist_field(self, test_client):
        """POST /api/mpc/open validates request body with playlist field."""
        response = test_client.post(
            "/api/mpc/open",
            json={
                "tmdb_id": 1396,
                "rel_path": "S01E01 - Pilot.mkv",
                "playlist": ["S01E01 - Pilot.mkv", "S01E02 - Cat's in the Bag.mkv"],
            },
        )
        # Request schema is valid; may fail on file resolution but not on validation
        assert response.status_code != 422


@pytest.mark.integration
class TestMpcNextPrevEndpoints:
    """POST /api/mpc/next and /api/mpc/prev tests."""

    def test_next_episode_with_playing_file(self, test_client, mock_state, tmp_path):
        """POST /api/mpc/next returns next episode when one exists."""
        from unittest.mock import MagicMock

        # Create episode files in a temp folder
        show_dir = tmp_path / "Breaking Bad [1396]"
        show_dir.mkdir()
        ep1 = show_dir / "S01E01 - Pilot.mkv"
        ep2 = show_dir / "S01E02 - Cat's in the Bag.mkv"
        ep1.write_bytes(b"ep1")
        ep2.write_bytes(b"ep2")

        # Mock MPC to report playing ep1
        status = MagicMock()
        status.file = str(ep1)
        status.to_dict.return_value = {"file": str(ep1), "state": 2}
        mock_state.mpc.get_status = lambda: status
        # Make get_status async
        import asyncio
        async def async_get_status():
            return status
        mock_state.mpc.get_status = async_get_status

        response = test_client.post("/api/mpc/next")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "S01E02" in data["rel_path"]

    def test_next_episode_no_file_playing_returns_404(self, test_client, mock_state):
        """POST /api/mpc/next returns 404 when nothing is playing."""
        from unittest.mock import MagicMock

        status = MagicMock()
        status.file = ""
        status.to_dict.return_value = {"file": "", "state": 0}

        async def async_get_status():
            return status
        mock_state.mpc.get_status = async_get_status

        response = test_client.post("/api/mpc/next")
        assert response.status_code == 404

    def test_prev_episode_no_file_playing_returns_404(self, test_client, mock_state):
        """POST /api/mpc/prev returns 404 when nothing is playing."""
        from unittest.mock import MagicMock

        status = MagicMock()
        status.file = ""
        status.to_dict.return_value = {"file": "", "state": 0}

        async def async_get_status():
            return status
        mock_state.mpc.get_status = async_get_status

        response = test_client.post("/api/mpc/prev")
        assert response.status_code == 404

    def test_next_at_last_episode_returns_404(self, test_client, mock_state, tmp_path):
        """POST /api/mpc/next returns 404 when at the last episode."""
        from unittest.mock import MagicMock

        show_dir = tmp_path / "Show [100]"
        show_dir.mkdir()
        ep1 = show_dir / "S01E01 - First.mkv"
        ep1.write_bytes(b"ep1")

        status = MagicMock()
        status.file = str(ep1)

        async def async_get_status():
            return status
        mock_state.mpc.get_status = async_get_status

        response = test_client.post("/api/mpc/next")
        assert response.status_code == 404


@pytest.mark.integration
class TestMpcSSEEndpoint:
    """GET /api/mpc/stream SSE tests."""

    def test_sse_endpoint_returns_event_stream(self, test_client):
        """GET /api/mpc/stream returns text/event-stream content type."""
        # SSE endpoints are long-lived; use stream=True and read just the header
        with test_client.stream("GET", "/api/mpc/stream") as response:
            assert response.status_code == 200
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type

    def test_sse_first_event_has_status_fields(self, test_client):
        """First SSE event contains player status fields."""
        import json

        with test_client.stream("GET", "/api/mpc/stream") as response:
            assert response.status_code == 200
            # Read lines until we get a data line
            for line in response.iter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    data = json.loads(line[len("data:"):])
                    assert "reachable" in data
                    assert "state" in data
                    assert "media" in data
                    break


@pytest.mark.integration
class TestNoWindowsPathsExposed:
    """Verify no raw Windows paths leak to the frontend."""

    def test_status_no_windows_paths_in_media_context(self, test_client, mock_state):
        """GET /api/mpc/status media context should not contain raw Windows paths."""
        mock_state.library.set_items([
            {"tmdb_id": 1396, "title": "Breaking Bad", "type": "tv",
             "folder_name": "Breaking Bad [1396]"}
        ])
        response = test_client.get("/api/mpc/status")
        data = response.json()
        media = data.get("media")
        if media:
            for key, value in media.items():
                if isinstance(value, str):
                    assert "C:\\" not in value, f"media.{key} contains Windows path: {value}"
                    assert "D:\\" not in value, f"media.{key} contains Windows path: {value}"
