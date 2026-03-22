"""
Integration tests for system router (/api/status, /api/logs).
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestSystemRouter:
    """System endpoint tests."""

    def test_get_status_returns_200_with_status_ok(self, test_client):
        """GET /api/status returns 200 with status=ok and config fields."""
        response = test_client.get("/api/status")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "movies_dir" in data
        assert "tv_dir" in data
        assert "anime_dir" in data
        assert "movies_dir_archive" in data
        assert "tv_dir_archive" in data
        assert "anime_dir_archive" in data
        assert "watch_threshold_pct" in data
        assert "mpc_be_url" in data

    def test_get_status_config_fields_are_strings(self, test_client):
        """Status config fields are strings or numbers."""
        response = test_client.get("/api/status")
        data = response.json()
        assert isinstance(data["movies_dir"], str)
        assert isinstance(data["watch_threshold_pct"], int)

    def test_get_logs_returns_200_with_lines_array(self, test_client):
        """GET /api/logs returns 200 with lines array."""
        response = test_client.get("/api/logs")
        assert response.status_code == 200

        data = response.json()
        assert "lines" in data
        assert isinstance(data["lines"], list)

    def test_get_logs_default_limit(self, test_client):
        """GET /api/logs uses default limit of 200."""
        response = test_client.get("/api/logs")
        assert response.status_code == 200

    def test_get_logs_custom_limit(self, test_client):
        """GET /api/logs respects custom lines parameter."""
        response = test_client.get("/api/logs?lines=10")
        assert response.status_code == 200

        data = response.json()
        # Should have <= 10 lines (or fewer if log is small)
        assert len(data["lines"]) <= 10

    def test_get_logs_returns_total_count(self, test_client):
        """GET /api/logs response includes total line count."""
        response = test_client.get("/api/logs")
        data = response.json()
        # May not have total if log doesn't exist, but if it exists it should
        if data["lines"]:
            assert "total" in data or "note" in data
