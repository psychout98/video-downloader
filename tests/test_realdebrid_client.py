"""
Unit tests for server/clients/realdebrid_client.py.

Tests cover:
- RealDebridClient.is_cached
- RealDebridClient.add_magnet (success + failure)
- RealDebridClient.select_all_files (success + failure)
- RealDebridClient.wait_until_downloaded (success, error status, timeout)
- RealDebridClient.get_torrent_info
- RealDebridClient.unrestrict_link (success + failure)
- RealDebridClient.unrestrict_all
- RealDebridClient.download_magnet (full pipeline)
- RealDebridError exception
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

from server.clients.realdebrid_client import RealDebridClient, RealDebridError


# ── Helpers ───────────────────────────────────────────────────────────────


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ── RealDebridError ───────────────────────────────────────────────────────


class TestRealDebridError:
    def test_is_exception(self):
        err = RealDebridError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"


# ── RealDebridClient.is_cached ────────────────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridIsCached:
    async def test_cached_returns_true(self):
        client = RealDebridClient("fake_key")
        client.get = AsyncMock(return_value=_mock_response(
            json_data={"abc123": {"rd": [{"1": {"filename": "test.mkv"}}]}}
        ))
        result = await client.is_cached("ABC123")
        assert result is True
        await client.close()

    async def test_not_cached_returns_false(self):
        client = RealDebridClient("fake_key")
        client.get = AsyncMock(return_value=_mock_response(
            json_data={"abc123": {}}
        ))
        result = await client.is_cached("ABC123")
        assert result is False
        await client.close()

    async def test_api_error_returns_false(self):
        client = RealDebridClient("fake_key")
        client.get = AsyncMock(side_effect=Exception("API down"))
        result = await client.is_cached("ABC123")
        assert result is False
        await client.close()


# ── RealDebridClient.add_magnet ───────────────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridAddMagnet:
    async def test_success(self):
        client = RealDebridClient("fake_key")
        client.post = AsyncMock(return_value=_mock_response(
            status_code=201, json_data={"id": "torrent-123"}
        ))
        result = await client.add_magnet("magnet:?xt=urn:btih:abc123")
        assert result == "torrent-123"
        await client.close()

    async def test_failure_status(self):
        client = RealDebridClient("fake_key")
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal error"
        resp.json.return_value = {}
        client.post = AsyncMock(return_value=resp)

        with pytest.raises(RealDebridError, match="addMagnet failed"):
            await client.add_magnet("magnet:?xt=urn:btih:abc123")
        await client.close()

    async def test_no_id_in_response(self):
        client = RealDebridClient("fake_key")
        client.post = AsyncMock(return_value=_mock_response(
            status_code=200, json_data={}
        ))
        with pytest.raises(RealDebridError, match="no id"):
            await client.add_magnet("magnet:?xt=urn:btih:abc123")
        await client.close()


# ── RealDebridClient.select_all_files ─────────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridSelectAllFiles:
    async def test_success(self):
        client = RealDebridClient("fake_key")
        client.post = AsyncMock(return_value=_mock_response(status_code=204))
        await client.select_all_files("torrent-123")
        await client.close()

    async def test_failure(self):
        client = RealDebridClient("fake_key")
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "error"
        client.post = AsyncMock(return_value=resp)

        with pytest.raises(RealDebridError, match="selectFiles failed"):
            await client.select_all_files("torrent-123")
        await client.close()


# ── RealDebridClient.wait_until_downloaded ────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridWaitUntilDownloaded:
    async def test_already_downloaded(self):
        client = RealDebridClient("fake_key", poll_interval=0)
        client.get_torrent_info = AsyncMock(return_value={
            "status": "downloaded",
            "progress": 100,
            "links": ["https://rd.example.com/dl/file1"],
        })
        links = await client.wait_until_downloaded("torrent-123")
        assert links == ["https://rd.example.com/dl/file1"]
        await client.close()

    async def test_error_status_raises(self):
        client = RealDebridClient("fake_key", poll_interval=0)
        client.get_torrent_info = AsyncMock(return_value={
            "status": "error",
            "progress": 0,
        })
        with pytest.raises(RealDebridError, match="failed with status"):
            await client.wait_until_downloaded("torrent-123")
        await client.close()

    async def test_timeout_raises(self):
        client = RealDebridClient("fake_key", poll_interval=0)
        client.get_torrent_info = AsyncMock(return_value={
            "status": "downloading",
            "progress": 50,
        })
        with pytest.raises(RealDebridError, match="timed out"):
            await client.wait_until_downloaded("torrent-123", max_wait=0)
        await client.close()

    async def test_downloaded_no_links_raises(self):
        client = RealDebridClient("fake_key", poll_interval=0)
        client.get_torrent_info = AsyncMock(return_value={
            "status": "downloaded",
            "progress": 100,
            "links": [],
        })
        with pytest.raises(RealDebridError, match="no links"):
            await client.wait_until_downloaded("torrent-123")
        await client.close()

    async def test_progress_callback(self):
        client = RealDebridClient("fake_key", poll_interval=0)
        call_count = 0

        async def on_progress(pct):
            nonlocal call_count
            call_count += 1

        client.get_torrent_info = AsyncMock(return_value={
            "status": "downloaded",
            "progress": 100,
            "links": ["https://example.com/dl"],
        })
        await client.wait_until_downloaded("torrent-123", on_progress=on_progress)
        assert call_count == 1
        await client.close()


# ── RealDebridClient.unrestrict_link ──────────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridUnrestrictLink:
    async def test_success(self):
        client = RealDebridClient("fake_key")
        client.post = AsyncMock(return_value=_mock_response(
            json_data={"download": "https://cdn.example.com/file.mkv", "filesize": 5000000}
        ))
        url, size = await client.unrestrict_link("https://rd.example.com/dl/123")
        assert url == "https://cdn.example.com/file.mkv"
        assert size == 5000000
        await client.close()

    async def test_failure_status(self):
        client = RealDebridClient("fake_key")
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "Forbidden"
        resp.json.return_value = {}
        client.post = AsyncMock(return_value=resp)

        with pytest.raises(RealDebridError, match="unrestrict/link failed"):
            await client.unrestrict_link("https://rd.example.com/dl/123")
        await client.close()

    async def test_no_url_in_response(self):
        client = RealDebridClient("fake_key")
        client.post = AsyncMock(return_value=_mock_response(json_data={}))
        with pytest.raises(RealDebridError, match="no URL"):
            await client.unrestrict_link("https://rd.example.com/dl/123")
        await client.close()


# ── RealDebridClient.unrestrict_all ───────────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridUnrestrictAll:
    async def test_unrestricts_multiple_links(self):
        client = RealDebridClient("fake_key")
        client.unrestrict_link = AsyncMock(side_effect=[
            ("https://cdn1.com/file1.mkv", 1000),
            ("https://cdn2.com/file2.mkv", 2000),
        ])
        results = await client.unrestrict_all(["link1", "link2"])
        assert len(results) == 2
        assert results[0] == ("https://cdn1.com/file1.mkv", 1000)
        await client.close()


# ── RealDebridClient.download_magnet ──────────────────────────────────────


@pytest.mark.asyncio
class TestRealDebridDownloadMagnet:
    async def test_full_pipeline(self):
        client = RealDebridClient("fake_key", poll_interval=0)
        client.add_magnet = AsyncMock(return_value="torrent-123")
        client.select_all_files = AsyncMock()
        client.wait_until_downloaded = AsyncMock(return_value=["link1", "link2"])
        client.unrestrict_all = AsyncMock(return_value=[
            ("https://cdn1.com/f1.mkv", 1000),
            ("https://cdn2.com/f2.mkv", 2000),
        ])

        files, tid = await client.download_magnet("magnet:?xt=urn:btih:abc123")
        assert tid == "torrent-123"
        assert len(files) == 2
        await client.close()
