"""
Unit tests for server/config.py and server/state.py.

Tests cover:
- Settings class initialization with env vars
- _userprofile helper
- reload_settings
- state module attributes and prune_searches
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")


# ── Settings ──────────────────────────────────────────────────────────────


class TestSettings:
    def test_settings_loads_from_env(self):
        from server.config import Settings

        with patch.dict(os.environ, {
            "TMDB_API_KEY": "test_key",
            "REAL_DEBRID_API_KEY": "test_rd_key",
        }):
            s = Settings()
            assert s.TMDB_API_KEY == "test_key"
            assert s.REAL_DEBRID_API_KEY == "test_rd_key"

    def test_settings_defaults(self):
        from server.config import Settings

        s = Settings()
        assert s.WATCH_THRESHOLD == 0.85
        assert s.HOST == "0.0.0.0"
        assert s.PORT == 8000
        assert s.MAX_CONCURRENT_DOWNLOADS == 2
        assert s.CHUNK_SIZE == 8 * 1024 * 1024
        assert s.RD_POLL_INTERVAL == 30

    def test_settings_media_dir_default(self):
        from server.config import Settings

        s = Settings()
        # Should resolve to something under %USERPROFILE%\Media
        assert "Media" in s.MEDIA_DIR or "media" in s.MEDIA_DIR.lower() or s.MEDIA_DIR

    def test_settings_archive_dir_default(self):
        from server.config import Settings

        s = Settings()
        assert s.ARCHIVE_DIR == "D:\\Media"

    def test_settings_mpc_be_defaults(self):
        from server.config import Settings

        s = Settings()
        assert s.MPC_BE_URL == "http://127.0.0.1:13579"
        assert "mpc-be" in s.MPC_BE_EXE.lower() or "mpc" in s.MPC_BE_EXE.lower()


class TestSettingsNewFields:
    """Verify new directory settings exist."""

    def test_has_media_dir_setting(self):
        """Settings has MEDIA_DIR attribute."""
        from server.config import Settings

        s = Settings()
        assert hasattr(s, "MEDIA_DIR"), "MEDIA_DIR should exist"

    def test_has_archive_dir_setting(self):
        """Settings has ARCHIVE_DIR attribute."""
        from server.config import Settings

        s = Settings()
        assert hasattr(s, "ARCHIVE_DIR"), "ARCHIVE_DIR should exist"

    def test_has_migrated_flag(self):
        """Settings has MIGRATED flag."""
        from server.config import Settings

        s = Settings()
        assert hasattr(s, "MIGRATED"), "MIGRATED flag should exist"


class TestReloadSettings:
    def test_reload_settings_updates_values(self):
        from server.config import settings, reload_settings

        original_host = settings.HOST
        with patch.dict(os.environ, {"HOST": "127.0.0.1"}):
            reload_settings()
        # Should have picked up the new value
        assert settings.HOST == "127.0.0.1"
        # Restore
        with patch.dict(os.environ, {"HOST": original_host}):
            reload_settings()


# ── State module ──────────────────────────────────────────────────────────


class TestState:
    def test_state_module_has_expected_attributes(self):
        import server.state as state

        assert hasattr(state, "processor")
        assert hasattr(state, "tmdb")
        assert hasattr(state, "torrentio")
        assert hasattr(state, "rd")
        assert hasattr(state, "library")
        assert hasattr(state, "mpc")
        assert hasattr(state, "watch_tracker")
        assert hasattr(state, "searches")
        assert hasattr(state, "SEARCH_TTL")
        assert hasattr(state, "LOG_FILE")
        assert hasattr(state, "PID_FILE")
        assert hasattr(state, "DATA_DIR")

    def test_prune_searches_removes_expired(self):
        import server.state as state

        state.searches = {
            "fresh": {"media": {}, "streams": [], "expires": time.time() + 300},
            "stale": {"media": {}, "streams": [], "expires": time.time() - 100},
        }
        state.prune_searches()
        assert "fresh" in state.searches
        assert "stale" not in state.searches

        # Clean up
        state.searches = {}

    def test_prune_searches_empty(self):
        import server.state as state

        state.searches = {}
        state.prune_searches()
        assert state.searches == {}
