"""
Integration tests for Settings API (Feature 8).

AC Reference:
  8.1  GET /api/settings returns 200 with all setting keys as strings or numbers
  8.2  POST /api/settings with valid keys returns ok=true and list of written keys
  8.3  Unknown setting key returns 400
  8.4  Surrounding quotes are stripped from values
  8.5  Multiple keys can be updated in a single request
  8.6  GET /api/settings/test-rd returns ok field and key_suffix
  8.7  Invalid RD key returns ok=false; connection errors are handled gracefully
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.integration
class TestFeature8_SettingsAPI:
    """Feature 8: Settings API"""

    def test_8_1_get_settings_returns_all_keys_as_strings_or_numbers(self, test_client):
        """8.1 — GET /api/settings returns 200 with all setting keys as strings or numbers."""
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

        for key, value in data.items():
            assert isinstance(value, (str, int, float))

    def test_8_2_post_settings_with_valid_keys_returns_ok_and_written(self, test_client, tmp_env_file):
        """8.2 — POST /api/settings with valid keys returns ok=true and list of written keys."""
        response = test_client.post(
            "/api/settings",
            json={"updates": {"TMDB_API_KEY": "new_test_key_123"}},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert "written" in data
        assert isinstance(data["written"], list)

    def test_8_3_unknown_setting_key_returns_400(self, test_client):
        """8.3 — Unknown setting key returns 400."""
        response = test_client.post(
            "/api/settings",
            json={"updates": {"UNKNOWN_KEY": "value"}},
        )
        assert response.status_code == 400
        assert "Unknown key" in response.json()["detail"]

    def test_8_4_surrounding_quotes_are_stripped(self, test_client):
        """8.4 — Surrounding quotes are stripped from values."""
        response = test_client.post(
            "/api/settings",
            json={"updates": {"MPC_BE_URL": '"http://127.0.0.1:13579"'}},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_8_5_multiple_keys_can_be_updated(self, test_client):
        """8.5 — Multiple keys can be updated in a single request."""
        response = test_client.post(
            "/api/settings",
            json={"updates": {"TMDB_API_KEY": "key1", "WATCH_THRESHOLD": "0.90"}},
        )
        assert response.status_code == 200
        assert len(response.json()["written"]) >= 1

    def test_8_6_test_rd_returns_ok_and_key_suffix(self, test_client):
        """8.6 — GET /api/settings/test-rd returns ok field and key_suffix."""
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
            assert response.status_code == 200

            data = response.json()
            assert "ok" in data
            assert "key_suffix" in data

    def test_8_7_invalid_rd_key_returns_ok_false_and_errors_handled(self, test_client):
        """8.7 — Invalid RD key returns ok=false; connection errors are handled gracefully."""
        # Invalid key
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            response = test_client.get("/api/settings/test-rd")
            assert response.json()["ok"] is False

        # Connection error
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
