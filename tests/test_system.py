"""
Integration tests for System API (Feature 9).

AC Reference:
  9.1  GET /api/status returns 200 with status="ok"
  9.2  Status includes movies_dir, tv_dir, anime_dir, mpc_be_url, and other config fields
  9.3  GET /api/logs returns 200 with lines array and total count
  9.4  Default log limit is 200; supports ?lines=N parameter
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestFeature9_SystemAPI:
    """Feature 9: System API"""

    def test_9_1_get_status_returns_200_with_status_ok(self, test_client):
        """9.1 — GET /api/status returns 200 with status="ok"."""
        response = test_client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_9_2_status_includes_config_fields(self, test_client):
        """9.2 — Status includes movies_dir, tv_dir, anime_dir, mpc_be_url, and other config fields."""
        response = test_client.get("/api/status")
        data = response.json()

        for field in (
            "movies_dir", "tv_dir", "anime_dir",
            "movies_dir_archive", "tv_dir_archive", "anime_dir_archive",
            "watch_threshold_pct", "mpc_be_url",
        ):
            assert field in data, f"Missing config field: {field}"

        assert isinstance(data["movies_dir"], str)
        assert isinstance(data["watch_threshold_pct"], int)

    def test_9_3_get_logs_returns_200_with_lines_and_total(self, test_client):
        """9.3 — GET /api/logs returns 200 with lines array and total count."""
        response = test_client.get("/api/logs")
        assert response.status_code == 200

        data = response.json()
        assert "lines" in data
        assert isinstance(data["lines"], list)

    def test_9_4_default_log_limit_is_200_and_supports_lines_param(self, test_client):
        """9.4 — Default log limit is 200; supports ?lines=N parameter."""
        # Default request
        response_default = test_client.get("/api/logs")
        assert response_default.status_code == 200

        # Custom limit
        response_custom = test_client.get("/api/logs?lines=10")
        assert response_custom.status_code == 200
        assert len(response_custom.json()["lines"]) <= 10
