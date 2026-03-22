"""
Unit tests for settings router helper functions (server/routers/settings.py).

Tests cover:
- _write_env_key (with dotenv set_key)
- _manual_write_env_key (fallback writer)
- _verify_env_file (read-back verification)
- _reinit_clients (client re-initialization after settings change)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.routers.settings import (
    _write_env_key,
    _manual_write_env_key,
    _verify_env_file,
    _reinit_clients,
)


# ── _write_env_key ──────────────────────────────────────────────────────


class TestWriteEnvKey:
    def test_writes_key_value_to_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_KEY=value\n")

        _write_env_key(str(env_file), "NEW_KEY", "new_value")

        content = env_file.read_text()
        assert "NEW_KEY" in content

    def test_falls_back_on_type_error(self, tmp_path):
        """When dotenv's set_key doesn't support quote_mode, falls back to manual."""
        env_file = tmp_path / ".env"
        env_file.write_text("")

        # Patch where set_key is actually looked up: in the dotenv module
        with patch("dotenv.set_key", side_effect=TypeError("unexpected keyword")):
            _write_env_key(str(env_file), "KEY", "value")

        # Fallback manual writer should have written the key
        content = env_file.read_text()
        assert "KEY=value" in content


# ── _manual_write_env_key ───────────────────────────────────────────────


class TestManualWriteEnvKey:
    def test_appends_new_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING=old\n")

        _manual_write_env_key(str(env_file), "NEW_KEY", "new_value")

        content = env_file.read_text()
        assert "EXISTING=old" in content
        assert "NEW_KEY=new_value" in content

    def test_updates_existing_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MY_KEY=old_value\nOTHER=keep\n")

        _manual_write_env_key(str(env_file), "MY_KEY", "updated")

        content = env_file.read_text()
        assert "MY_KEY=updated" in content
        assert "old_value" not in content
        assert "OTHER=keep" in content

    def test_creates_entry_in_empty_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.touch()

        _manual_write_env_key(str(env_file), "KEY", "value")

        content = env_file.read_text()
        assert "KEY=value" in content

    def test_no_quoting_in_output(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        _manual_write_env_key(str(env_file), "URL", "http://127.0.0.1:8000")

        content = env_file.read_text()
        assert "URL=http://127.0.0.1:8000" in content
        assert "'" not in content

    def test_handles_spaces_in_key_pattern(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MY_KEY = old_value\n")

        _manual_write_env_key(str(env_file), "MY_KEY", "new_value")

        content = env_file.read_text()
        assert "MY_KEY=new_value" in content


# ── _verify_env_file ────────────────────────────────────────────────────


class TestVerifyEnvFile:
    def test_no_errors_for_clean_values(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=value\nURL=http://localhost:8000\n")

        errors = _verify_env_file(str(env_file), {"KEY": "value", "URL": "http://localhost:8000"})
        assert errors == []

    def test_detects_single_quote_wrapping(self, tmp_path):
        """_verify_env_file detects values with unwanted single quotes."""
        env_file = tmp_path / ".env"
        # dotenv_values strips matching outer quotes, so KEY='val' → val.
        # To trigger the check (actual_value.startswith("'")), we need a value
        # whose parsed result starts with a single quote. An unmatched leading
        # quote achieves this: KEY='val  → 'val
        env_file.write_text("KEY='unmatched_value\n")

        errors = _verify_env_file(str(env_file), {"KEY": "unmatched_value"})
        assert len(errors) >= 1
        assert "single quotes" in errors[0]

    def test_handles_missing_key_in_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")

        # Missing key returns empty actual_value — no quote error triggered
        errors = _verify_env_file(str(env_file), {"MISSING": "value"})
        assert errors == []

    def test_clean_value_no_errors(self, tmp_path):
        env_file = tmp_path / ".env"
        _manual_write_env_key(str(env_file), "KEY", "clean_value")

        errors = _verify_env_file(str(env_file), {"KEY": "clean_value"})
        assert errors == []


# ── _reinit_clients ─────────────────────────────────────────────────────


class TestReinitClients:
    def test_reinit_replaces_tmdb_client(self):
        import server.state as state_mod

        with patch.object(state_mod, "tmdb", MagicMock()), \
             patch.object(state_mod, "torrentio", MagicMock()), \
             patch.object(state_mod, "rd", MagicMock()), \
             patch.object(state_mod, "processor", None), \
             patch("server.routers.settings.settings") as mock_settings, \
             patch("server.clients.tmdb_client.TMDBClient") as MockTMDB, \
             patch("server.clients.torrentio_client.TorrentioClient") as MockTorrentio, \
             patch("server.clients.realdebrid_client.RealDebridClient") as MockRD:
            mock_settings.TMDB_API_KEY = "new_key"
            mock_settings.REAL_DEBRID_API_KEY = "new_rd_key"
            mock_settings.RD_POLL_INTERVAL = 30

            _reinit_clients()

            MockTMDB.assert_called_once_with("new_key")
            MockTorrentio.assert_called_once_with("new_rd_key")
            MockRD.assert_called_once_with("new_rd_key", poll_interval=30)

    def test_reinit_skips_none_clients(self):
        import server.state as state_mod

        with patch.object(state_mod, "tmdb", None), \
             patch.object(state_mod, "torrentio", None), \
             patch.object(state_mod, "rd", None), \
             patch.object(state_mod, "processor", None), \
             patch("server.clients.tmdb_client.TMDBClient") as MockTMDB, \
             patch("server.clients.torrentio_client.TorrentioClient") as MockTorrentio, \
             patch("server.clients.realdebrid_client.RealDebridClient") as MockRD:
            _reinit_clients()

            MockTMDB.assert_not_called()
            MockTorrentio.assert_not_called()
            MockRD.assert_not_called()

    def test_reinit_updates_processor_references(self):
        import server.state as state_mod

        mock_proc = MagicMock()
        with patch.object(state_mod, "tmdb", MagicMock()), \
             patch.object(state_mod, "torrentio", MagicMock()), \
             patch.object(state_mod, "rd", MagicMock()), \
             patch.object(state_mod, "processor", mock_proc), \
             patch("server.routers.settings.settings") as mock_settings, \
             patch("server.clients.tmdb_client.TMDBClient") as MockTMDB, \
             patch("server.clients.torrentio_client.TorrentioClient"), \
             patch("server.clients.realdebrid_client.RealDebridClient"):
            mock_settings.TMDB_API_KEY = "key"
            mock_settings.REAL_DEBRID_API_KEY = "rd_key"
            mock_settings.RD_POLL_INTERVAL = 30

            _reinit_clients()

            # Assert inside the with block before patches are reverted
            # Processor._tmdb should be set to the new TMDBClient instance
            assert mock_proc._tmdb == MockTMDB.return_value
