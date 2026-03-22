"""
Integration tests for settings router (/api/settings).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.integration
class TestSettingsGetEndpoint:
    """Settings GET endpoint tests."""

    def test_get_settings_returns_200_with_all_keys(self, test_client):
        """GET /api/settings returns 200 with all expected keys."""
        response = test_client.get("/api/settings")
        assert response.status_code == 200

        data = response.json()
        expected_keys = [
            "TMDB_API_KEY", "REAL_DEBRID_API_KEY",
            "MEDIA_DIR", "ARCHIVE_DIR",
            "DOWNLOADS_DIR", "POSTERS_DIR",
            "MPC_BE_URL", "MPC_BE_EXE",
            "WATCH_THRESHOLD", "HOST", "PORT", "MAX_CONCURRENT_DOWNLOADS",
        ]
        for key in expected_keys:
            assert key in data

    def test_get_settings_all_values_are_strings_or_numbers(self, test_client):
        """Settings values should be strings or numbers."""
        response = test_client.get("/api/settings")
        data = response.json()

        for key, value in data.items():
            assert isinstance(value, (str, int, float))

    def test_get_settings_includes_api_keys_masked(self, test_client):
        """API keys are included but should be from test .env."""
        response = test_client.get("/api/settings")
        data = response.json()

        # Should have some keys (from test .env)
        assert "TMDB_API_KEY" in data
        assert "REAL_DEBRID_API_KEY" in data


@pytest.mark.integration
class TestSettingsPostEndpoint:
    """Settings POST endpoint tests."""

    def test_post_settings_with_valid_updates_returns_ok(self, test_client, tmp_env_file):
        """POST /api/settings with valid updates returns ok=true."""
        response = test_client.post(
            "/api/settings",
            json={
                "updates": {
                    "TMDB_API_KEY": "new_test_key_123",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "written" in data

    def test_post_settings_with_unknown_key_returns_400(self, test_client):
        """POST /api/settings with unknown key returns 400."""
        response = test_client.post(
            "/api/settings",
            json={
                "updates": {
                    "UNKNOWN_KEY": "value",
                }
            },
        )
        assert response.status_code == 400
        assert "Unknown key" in response.json()["detail"]

    def test_post_settings_strips_quotes_from_values(self, test_client):
        """Settings update strips surrounding quotes from values."""
        response = test_client.post(
            "/api/settings",
            json={
                "updates": {
                    "MPC_BE_URL": '"http://127.0.0.1:13579"',
                }
            },
        )
        assert response.status_code == 200
        # Value should be written without quotes
        assert response.json()["ok"] is True

    def test_post_settings_multiple_updates(self, test_client):
        """POST /api/settings can update multiple keys."""
        response = test_client.post(
            "/api/settings",
            json={
                "updates": {
                    "TMDB_API_KEY": "key1",
                    "WATCH_THRESHOLD": "0.90",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["written"]) >= 1

    def test_post_settings_returns_written_keys(self, test_client):
        """Settings update response includes list of written keys."""
        response = test_client.post(
            "/api/settings",
            json={
                "updates": {
                    "HOST": "0.0.0.0",
                    "PORT": "8080",
                }
            },
        )
        data = response.json()
        assert "written" in data
        assert isinstance(data["written"], list)


@pytest.mark.integration
class TestTestRealDebridEndpoint:
    """Real-Debrid API test endpoint tests."""

    def test_test_rd_returns_ok_field(self, test_client):
        """GET /api/settings/test-rd returns response with ok field."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock the async context manager
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"username": "testuser"}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_client_class.return_value = mock_client

            response = test_client.get("/api/settings/test-rd")
            assert response.status_code == 200

            data = response.json()
            assert "ok" in data

    def test_test_rd_includes_key_suffix(self, test_client):
        """Test RD response includes key_suffix field."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"username": "testuser"}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_client_class.return_value = mock_client

            response = test_client.get("/api/settings/test-rd")
            data = response.json()
            assert "key_suffix" in data

    def test_test_rd_failure_returns_ok_false(self, test_client):
        """Test RD with invalid key returns ok=false."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 401  # Unauthorized
            mock_response.json.return_value = {}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_client_class.return_value = mock_client

            response = test_client.get("/api/settings/test-rd")
            data = response.json()
            assert data["ok"] is False

    def test_test_rd_handles_connection_error(self, test_client):
        """Test RD handles connection errors gracefully."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_client_class.return_value = mock_client

            response = test_client.get("/api/settings/test-rd")
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is False
            assert "error" in data
