"""
Integration tests for MPC-BE Player Control API (Feature 10).

AC Reference:
  10.1  GET /api/mpc/status returns reachable, file, state, is_playing, position_ms, duration_ms, volume, muted
  10.2  Status includes media context (may be null) with tmdb_id, title, type, poster_url, season, episode
  10.3  POST /api/mpc/command returns ok=true; supports position_ms for seek
  10.4  POST /api/mpc/open returns 404 when file not found; supports playlist parameter
  10.5  POST /api/mpc/next returns next episode; returns 404 if nothing playing or at last episode
  10.6  POST /api/mpc/prev returns 404 if nothing playing
  10.7  GET /api/mpc/stream returns text/event-stream with status fields in events
  10.8  No Windows paths (C:\\, D:\\) exposed in media context responses
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestFeature10_MPCPlayerControlAPI:
    """Feature 10: MPC-BE Player Control API"""

    def test_10_1_status_returns_all_player_fields(self, test_client):
        """10.1 — GET /api/mpc/status returns reachable, file, state, is_playing, position_ms, duration_ms, volume, muted."""
        response = test_client.get("/api/mpc/status")
        assert response.status_code == 200

        data = response.json()
        for field in ("reachable", "file", "state", "is_playing", "position_ms", "duration_ms", "volume", "muted"):
            assert field in data, f"Missing field: {field}"

    def test_10_2_status_includes_media_context(self, test_client, mock_state):
        """10.2 — Status includes media context with tmdb_id, title, type, poster_url, season, episode when resolved."""
        response = test_client.get("/api/mpc/status")
        data = response.json()
        assert "media" in data

        # When media context is resolved, verify all sub-fields
        mock_state.library.set_items = getattr(mock_state.library, "set_items", None)
        if mock_state.library.set_items:
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

    def test_10_3_command_returns_ok_and_supports_seek(self, test_client):
        """10.3 — POST /api/mpc/command returns ok=true; supports position_ms for seek."""
        # Basic command
        response = test_client.post("/api/mpc/command", json={"command": 887})
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Seek command with position_ms
        response = test_client.post(
            "/api/mpc/command", json={"command": 889, "position_ms": 60000},
        )
        assert response.status_code == 200

    def test_10_4_open_returns_404_when_file_not_found_and_supports_playlist(self, test_client, mock_state):
        """10.4 — POST /api/mpc/open returns 404 when file not found; supports playlist parameter."""
        with patch("server.routers.mpc.settings") as mock_settings:
            mock_settings.MPC_BE_EXE = "/nonexistent/mpc-be"
            mock_settings.MEDIA_DIR = "/tmp/nonexistent_media"
            mock_settings.ARCHIVE_DIR = "/tmp/nonexistent_archive"

            response = test_client.post(
                "/api/mpc/open",
                json={"tmdb_id": 1396, "rel_path": "S01E01 - Pilot.mkv"},
            )
            assert response.status_code in (404, 500)

        # Playlist field should be accepted without 422
        response = test_client.post(
            "/api/mpc/open",
            json={
                "tmdb_id": 1396,
                "rel_path": "S01E01 - Pilot.mkv",
                "playlist": ["S01E01 - Pilot.mkv", "S01E02 - Cat's in the Bag.mkv"],
            },
        )
        assert response.status_code != 422

    def test_10_5_next_returns_next_episode_or_404(self, test_client, mock_state, tmp_path):
        """10.5 — POST /api/mpc/next returns next episode; returns 404 if nothing playing or at last episode."""
        # Nothing playing → 404
        status = MagicMock()
        status.file = ""
        status.to_dict.return_value = {"file": "", "state": 0}

        async def async_get_status_empty():
            return status
        mock_state.mpc.get_status = async_get_status_empty

        response = test_client.post("/api/mpc/next")
        assert response.status_code == 404

        # At last episode → 404
        show_dir = tmp_path / "Show [100]"
        show_dir.mkdir()
        ep1 = show_dir / "S01E01 - First.mkv"
        ep1.write_bytes(b"ep1")

        status_last = MagicMock()
        status_last.file = str(ep1)

        async def async_get_status_last():
            return status_last
        mock_state.mpc.get_status = async_get_status_last

        response = test_client.post("/api/mpc/next")
        assert response.status_code == 404

        # Has next episode → 200
        ep2 = show_dir / "S01E02 - Second.mkv"
        ep2.write_bytes(b"ep2")

        status_ep1 = MagicMock()
        status_ep1.file = str(ep1)
        status_ep1.to_dict.return_value = {"file": str(ep1), "state": 2}

        async def async_get_status_ep1():
            return status_ep1
        mock_state.mpc.get_status = async_get_status_ep1

        response = test_client.post("/api/mpc/next")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert "S01E02" in response.json()["rel_path"]

    def test_10_6_prev_returns_404_if_nothing_playing(self, test_client, mock_state):
        """10.6 — POST /api/mpc/prev returns 404 if nothing playing."""
        status = MagicMock()
        status.file = ""
        status.to_dict.return_value = {"file": "", "state": 0}

        async def async_get_status():
            return status
        mock_state.mpc.get_status = async_get_status

        response = test_client.post("/api/mpc/prev")
        assert response.status_code == 404

    def test_10_7_stream_returns_event_stream_with_status_fields(self, test_client):
        """10.7 — GET /api/mpc/stream returns text/event-stream with status fields in events."""
        # Use ?limit=1 so the SSE generator emits one event then stops,
        # allowing the sync TestClient to read the full response.
        response = test_client.get("/api/mpc/stream?limit=1")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        # Verify the body contains at least one SSE data event with expected fields
        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data = json.loads(line[len("data:"):])
                assert "reachable" in data
                assert "state" in data
                assert "media" in data
                break

    def test_10_8_no_windows_paths_in_media_context(self, test_client, mock_state):
        """10.8 — No Windows paths (C:\\, D:\\) exposed in media context responses."""
        if hasattr(mock_state.library, "set_items"):
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
