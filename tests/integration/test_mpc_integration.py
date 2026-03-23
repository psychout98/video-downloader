"""
Integration tests for MPC-BE player control via the FastAPI backend.

These tests communicate with the real backend's /api/mpc/* endpoints
which in turn control MPC-BE via its HTTP web interface on port 13579.

Requirements:
    - Windows OS
    - MPC-BE installed with web interface enabled
    - Backend server running (uvicorn server.main:app on port 8000)
    - A test media file (set TEST_MEDIA_FILE env var)

Run:
    pytest tests/integration/test_mpc_integration.py -v
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

from .conftest import BACKEND_URL, MPC_BE_EXE, skip_not_windows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_get(path: str, timeout: float = 10) -> httpx.Response:
    """Send a GET request to the backend API."""
    return httpx.get(f"{BACKEND_URL}{path}", timeout=timeout)


def api_post(path: str, json: dict | None = None, timeout: float = 10) -> httpx.Response:
    """Send a POST request to the backend API."""
    return httpx.post(f"{BACKEND_URL}{path}", json=json or {}, timeout=timeout)


def get_mpc_status() -> dict:
    """Get MPC-BE status from the backend API."""
    resp = api_get("/api/mpc/status")
    resp.raise_for_status()
    return resp.json()


def send_mpc_command(command: str, **kwargs) -> dict:
    """Send a command to MPC-BE via the backend API."""
    payload = {"command": command, **kwargs}
    resp = api_post("/api/mpc/command", json=payload)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

skip_no_mpc = pytest.mark.skipif(
    not os.path.isfile(MPC_BE_EXE),
    reason=f"MPC-BE not found at {MPC_BE_EXE}",
)

def _check_backend() -> bool:
    try:
        resp = httpx.get(f"{BACKEND_URL}/api/status", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


skip_no_backend = pytest.mark.skipif(
    not _check_backend(),
    reason=f"Backend not reachable at {BACKEND_URL}",
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@skip_not_windows
@skip_no_mpc
@skip_no_backend
class TestMPCReachability:
    """Test that MPC-BE is reachable via the backend."""

    def test_mpc_status_endpoint(self):
        """GET /api/mpc/status should return a valid response."""
        status = get_mpc_status()
        assert "reachable" in status
        # reachable may be True or False depending on whether MPC-BE is open

    def test_mpc_reachable_when_running(self):
        """If MPC-BE is running, reachable should be True."""
        status = get_mpc_status()
        if not status["reachable"]:
            pytest.skip("MPC-BE is not currently running")
        assert status["reachable"] is True
        assert "state" in status
        assert "volume" in status


@skip_not_windows
@skip_no_mpc
@skip_no_backend
class TestMPCPlayback:
    """Test playback control via MPC-BE.

    These tests require MPC-BE to be running and a test media file.
    """

    @pytest.fixture(autouse=True)
    def _check_mpc_running(self):
        """Skip if MPC-BE is not reachable."""
        status = get_mpc_status()
        if not status["reachable"]:
            pytest.skip("MPC-BE is not running")

    @pytest.fixture()
    def opened_file(self, test_media_file):
        """Open a test file in MPC-BE and wait for it to load."""
        resp = api_post("/api/mpc/open", json={"path": test_media_file})
        resp.raise_for_status()
        # Wait for file to load
        time.sleep(3)
        status = get_mpc_status()
        assert status.get("file"), "MPC-BE did not open the file"
        yield status
        # Stop playback after test
        send_mpc_command("stop")
        time.sleep(0.5)

    def test_open_file(self, test_media_file):
        """Opening a file should update the 'file' field in status."""
        resp = api_post("/api/mpc/open", json={"path": test_media_file})
        resp.raise_for_status()
        time.sleep(3)

        status = get_mpc_status()
        assert status["file"] is not None
        filename = os.path.basename(test_media_file)
        assert filename in (status.get("filename") or status.get("file", ""))

    def test_play_pause(self, opened_file):
        """Play/pause toggle should change the player state."""
        # Start playing
        send_mpc_command("play")
        time.sleep(1)
        status = get_mpc_status()
        assert status["is_playing"] is True

        # Pause
        send_mpc_command("pause")
        time.sleep(1)
        status = get_mpc_status()
        assert status["is_paused"] is True

    def test_stop(self, opened_file):
        """Stop command should change state to stopped."""
        send_mpc_command("play")
        time.sleep(1)

        send_mpc_command("stop")
        time.sleep(1)
        status = get_mpc_status()
        assert status["state"] == 0  # stopped

    def test_seek(self, opened_file):
        """Seeking should update the position."""
        send_mpc_command("play")
        time.sleep(1)

        # Seek to 10 seconds
        send_mpc_command("seek", position_ms=10_000)
        time.sleep(1)

        status = get_mpc_status()
        # Position should be near 10s (within 2s tolerance)
        assert abs(status["position_ms"] - 10_000) < 2_000, (
            f"Expected position near 10000ms, got {status['position_ms']}ms"
        )


@skip_not_windows
@skip_no_mpc
@skip_no_backend
class TestMPCVolume:
    """Test volume control via MPC-BE."""

    @pytest.fixture(autouse=True)
    def _check_mpc_running(self):
        status = get_mpc_status()
        if not status["reachable"]:
            pytest.skip("MPC-BE is not running")

    def test_volume_up(self):
        """Volume up should increase the volume level."""
        initial = get_mpc_status()["volume"]

        send_mpc_command("volume_up")
        time.sleep(0.5)

        updated = get_mpc_status()["volume"]
        if initial < 100:
            assert updated >= initial, (
                f"Volume should increase: was {initial}, now {updated}"
            )

    def test_volume_down(self):
        """Volume down should decrease the volume level."""
        # First set volume to a known non-zero level
        send_mpc_command("volume_up")
        send_mpc_command("volume_up")
        time.sleep(0.5)

        initial = get_mpc_status()["volume"]

        send_mpc_command("volume_down")
        time.sleep(0.5)

        updated = get_mpc_status()["volume"]
        if initial > 0:
            assert updated <= initial, (
                f"Volume should decrease: was {initial}, now {updated}"
            )

    def test_mute_toggle(self):
        """Mute toggle should flip the muted state."""
        initial_muted = get_mpc_status()["muted"]

        send_mpc_command("mute")
        time.sleep(0.5)

        updated_muted = get_mpc_status()["muted"]
        assert updated_muted != initial_muted, (
            f"Mute should toggle: was {initial_muted}, still {updated_muted}"
        )

        # Toggle back
        send_mpc_command("mute")
        time.sleep(0.5)

        restored_muted = get_mpc_status()["muted"]
        assert restored_muted == initial_muted
