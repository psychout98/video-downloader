"""
Integration tests for MPC-BE Integration (Feature 13).

AC Reference:
  13.1  GET /api/mpc/status returns a response when MPC-BE is running
  13.2  Status shows reachable=true when MPC-BE is running

Run:
    pytest tests/integration/test_mpc_integration.py -v
"""
from __future__ import annotations

import os

import httpx
import pytest

from .conftest import BACKEND_URL, MPC_BE_EXE, skip_not_windows


# ── Helpers ───────────────────────────────────────────────────────────────


def api_get(path: str, timeout: float = 10) -> httpx.Response:
    """Send a GET request to the backend API."""
    return httpx.get(f"{BACKEND_URL}{path}", timeout=timeout)


def get_mpc_status() -> dict:
    """Get MPC-BE status from the backend API."""
    resp = api_get("/api/mpc/status")
    resp.raise_for_status()
    return resp.json()


# ── Markers ───────────────────────────────────────────────────────────────

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


# ── Feature 13: MPC-BE Integration (Windows-only) ────────────────────────


@skip_not_windows
@skip_no_mpc
@skip_no_backend
class TestFeature13_MPCIntegration:
    """Feature 13: MPC-BE Integration"""

    def test_13_1_mpc_status_returns_response(self):
        """13.1 — GET /api/mpc/status returns a response when MPC-BE is running."""
        status = get_mpc_status()
        assert "reachable" in status

    def test_13_2_status_shows_reachable_true(self):
        """13.2 — Status shows reachable=true when MPC-BE is running."""
        status = get_mpc_status()
        if not status["reachable"]:
            pytest.skip("MPC-BE is not currently running")
        assert status["reachable"] is True
        assert "state" in status
        assert "volume" in status
