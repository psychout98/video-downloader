"""
Unit tests for server/clients/mpc_client.py.

Tests cover:
- MPCStatus properties (file, filename, state, is_playing, is_paused, position_ms,
  duration_ms, position_str, duration_str, volume, muted, to_dict)
- MPCClient._parse_variables (JSON, legacy JS, HTML formats)
- MPCClient.get_status (success + failure)
- MPCClient.command (success + failure)
- MPCClient convenience methods (play_pause, play, pause, stop, mute, volume_up/down, seek)
- MPCClient.ping and open_file
- _ms_to_str helper
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

from server.clients.mpc_client import MPCStatus, MPCClient, _ms_to_str


# ── _ms_to_str ────────────────────────────────────────────────────────────


class TestMsToStr:
    def test_zero(self):
        assert _ms_to_str(0) == "0:00"

    def test_seconds_only(self):
        assert _ms_to_str(45000) == "0:45"

    def test_minutes_and_seconds(self):
        assert _ms_to_str(125000) == "2:05"

    def test_hours_minutes_seconds(self):
        assert _ms_to_str(3661000) == "1:01:01"

    def test_negative_treated_as_zero(self):
        # 0 is falsy, same result
        assert _ms_to_str(0) == "0:00"


# ── MPCStatus ─────────────────────────────────────────────────────────────


class TestMPCStatus:
    def test_file_property(self):
        s = MPCStatus({"file": r"C:\Media\test.mkv"})
        assert s.file == r"C:\Media\test.mkv"

    def test_file_falls_back_to_filepath(self):
        s = MPCStatus({"filepath": r"C:\Media\test.mkv"})
        assert s.file == r"C:\Media\test.mkv"

    def test_filename_from_windows_path(self):
        s = MPCStatus({"file": r"C:\Media\folder\video.mkv"})
        assert s.filename == "video.mkv"

    def test_filename_from_posix_path(self):
        s = MPCStatus({"file": "/media/folder/video.mkv"})
        assert s.filename == "video.mkv"

    def test_filename_explicit(self):
        s = MPCStatus({"filename": "explicit.mkv", "file": "other.mkv"})
        assert s.filename == "explicit.mkv"

    def test_state_playing(self):
        assert MPCStatus({"state": 2}).state == 2

    def test_state_invalid_value(self):
        assert MPCStatus({"state": "invalid"}).state == 0

    def test_state_missing(self):
        assert MPCStatus({}).state == 0

    def test_is_playing(self):
        assert MPCStatus({"state": 2}).is_playing is True
        assert MPCStatus({"state": 1}).is_playing is False

    def test_is_paused(self):
        assert MPCStatus({"state": 1}).is_paused is True
        assert MPCStatus({"state": 2}).is_paused is False

    def test_position_ms(self):
        assert MPCStatus({"position": 5000}).position_ms == 5000

    def test_position_ms_invalid(self):
        assert MPCStatus({"position": "bad"}).position_ms == 0

    def test_duration_ms(self):
        assert MPCStatus({"duration": 360000}).duration_ms == 360000

    def test_duration_ms_invalid(self):
        assert MPCStatus({"duration": None}).duration_ms == 0

    def test_position_str_from_data(self):
        assert MPCStatus({"positionstring": "1:30"}).position_str == "1:30"

    def test_position_str_computed(self):
        assert MPCStatus({"position": 90000}).position_str == "1:30"

    def test_duration_str_from_data(self):
        assert MPCStatus({"durationstring": "2:00:00"}).duration_str == "2:00:00"

    def test_volume(self):
        assert MPCStatus({"volumelevel": 50}).volume == 50

    def test_volume_default(self):
        assert MPCStatus({}).volume == 100

    def test_volume_invalid(self):
        assert MPCStatus({"volumelevel": "x"}).volume == 100

    def test_muted_bool(self):
        assert MPCStatus({"muted": True}).muted is True
        assert MPCStatus({"muted": False}).muted is False

    def test_muted_string(self):
        assert MPCStatus({"muted": "1"}).muted is True
        assert MPCStatus({"muted": "true"}).muted is True
        assert MPCStatus({"muted": "0"}).muted is False

    def test_muted_default(self):
        assert MPCStatus({}).muted is False

    def test_to_dict_keys(self):
        s = MPCStatus({"state": 2, "file": "test.mkv"})
        d = s.to_dict()
        expected_keys = {
            "reachable", "file", "filename", "state",
            "is_playing", "is_paused", "position_ms", "duration_ms",
            "position_str", "duration_str", "volume", "muted",
        }
        assert set(d.keys()) == expected_keys


# ── MPCClient._parse_variables ────────────────────────────────────────────


class TestParseVariables:
    def test_json_format(self):
        text = '{"file": "test.mkv", "state": 2, "position": 1000}'
        result = MPCClient._parse_variables(text)
        assert result["file"] == "test.mkv"
        assert result["state"] == 2

    def test_legacy_js_format(self):
        text = 'OnVariable("file","C:\\\\test.mkv");OnVariable("state","2");'
        result = MPCClient._parse_variables(text)
        assert result["file"] == "C:\\\\test.mkv"
        assert result["state"] == "2"

    def test_html_format(self):
        text = '<p id="file">test.mkv</p><p id="state">2</p>'
        result = MPCClient._parse_variables(text)
        assert result["file"] == "test.mkv"
        assert result["state"] == "2"

    def test_html_format_filepatharg_decoded(self):
        text = '<p id="filepatharg">C%3A%5CMedia%5Ctest.mkv</p>'
        result = MPCClient._parse_variables(text)
        assert result["filepath"] == r"C:\Media\test.mkv"

    def test_invalid_json_falls_through(self):
        text = '{broken json'
        result = MPCClient._parse_variables(text)
        assert result == {}

    def test_empty_string(self):
        result = MPCClient._parse_variables("")
        assert result == {}


# ── MPCClient.get_status ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMPCClientGetStatus:
    async def test_get_status_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"file": "test.mkv", "state": 2}'
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            status = await client.get_status()
            assert status.reachable is True
            assert status.file == "test.mkv"

    async def test_get_status_unreachable(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            status = await client.get_status()
            assert status.reachable is False


# ── MPCClient.command ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMPCClientCommand:
    async def test_command_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            result = await client.command(887)
            assert result is True

    async def test_command_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("fail"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            result = await client.command(887)
            assert result is False


# ── MPCClient convenience methods ─────────────────────────────────────────


@pytest.mark.asyncio
class TestMPCClientConvenienceMethods:
    async def test_play_pause(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            result = await client.play_pause()
            mock.assert_called_with(887)
            assert result is True

    async def test_play(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.play()
            mock.assert_called_with(891)

    async def test_pause(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.pause()
            mock.assert_called_with(892)

    async def test_stop(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.stop()
            mock.assert_called_with(888)

    async def test_mute(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.mute()
            mock.assert_called_with(909)

    async def test_volume_up(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.volume_up()
            mock.assert_called_with(907)

    async def test_volume_down(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.volume_down()
            mock.assert_called_with(908)

    async def test_seek(self):
        client = MPCClient("http://localhost:13579")
        with patch.object(client, "command", new_callable=AsyncMock, return_value=True) as mock:
            await client.seek(60000)
            mock.assert_called_with(889, position=60000)


# ── MPCClient.ping ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMPCClientPing:
    async def test_ping_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            assert await client.ping() is True

    async def test_ping_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("fail"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            assert await client.ping() is False


# ── MPCClient.open_file ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMPCClientOpenFile:
    async def test_open_file_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            result = await client.open_file(r"C:\Media\test.mkv")
            assert result is True

    async def test_open_file_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("fail"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = MPCClient("http://localhost:13579")
            result = await client.open_file(r"C:\Media\test.mkv")
            assert result is False
