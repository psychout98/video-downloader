"""
Unit tests for server/clients/torrentio_client.py.

Tests cover:
- StreamResult dataclass
- _parse_size (GB, MB, TB)
- _parse_seeders
- TorrentioClient._build_url (movie, TV, cached/uncached)
- TorrentioClient.get_streams (success, no imdb_id, API failure, sorting)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.clients.torrentio_client import (
    StreamResult,
    _parse_size,
    _parse_seeders,
    TorrentioClient,
)
from server.clients.tmdb_client import MediaInfo


# ── _parse_size ───────────────────────────────────────────────────────────


class TestParseSize:
    def test_gb(self):
        assert _parse_size("💾 2.5 GB") == int(2.5 * 1024**3)

    def test_mb(self):
        assert _parse_size("💾 500 MB") == int(500 * 1024**2)

    def test_tb(self):
        assert _parse_size("💾 1.2 TB") == int(1.2 * 1024**4)

    def test_no_match(self):
        assert _parse_size("No size info") is None

    def test_case_insensitive(self):
        assert _parse_size("💾 2 gb") == int(2 * 1024**3)


# ── _parse_seeders ────────────────────────────────────────────────────────


class TestParseSeeders:
    def test_parses_seeders(self):
        assert _parse_seeders("👤 842 💾 52.3 GB") == 842

    def test_no_match(self):
        assert _parse_seeders("No seeder info") == 0


# ── StreamResult ──────────────────────────────────────────────────────────


class TestStreamResult:
    def test_defaults(self):
        s = StreamResult(name="Test")
        assert s.name == "Test"
        assert s.info_hash is None
        assert s.seeders == 0
        assert s.is_cached_rd is False
        assert s.magnet is None


# ── TorrentioClient._build_url ────────────────────────────────────────────


class TestBuildUrl:
    def test_movie_cached(self):
        client = TorrentioClient("fake_rd_key")
        media = MediaInfo(title="Inception", imdb_id="tt1375666", type="movie")
        url = client._build_url(media, cached_only=True)
        assert "realdebrid=fake_rd_key" in url
        assert "/movie/tt1375666.json" in url

    def test_movie_uncached(self):
        client = TorrentioClient("fake_rd_key")
        media = MediaInfo(title="Inception", imdb_id="tt1375666", type="movie")
        url = client._build_url(media, cached_only=False)
        assert "realdebrid" not in url
        assert "/movie/tt1375666.json" in url

    def test_tv_series(self):
        client = TorrentioClient("fake_rd_key")
        media = MediaInfo(
            title="Breaking Bad", imdb_id="tt0903747", type="tv", season=1, episode=3
        )
        url = client._build_url(media, cached_only=True)
        assert "/series/tt0903747:1:3.json" in url

    def test_tv_series_no_episode_defaults_to_1(self):
        client = TorrentioClient("fake_rd_key")
        media = MediaInfo(
            title="Breaking Bad", imdb_id="tt0903747", type="tv", season=1, episode=None
        )
        url = client._build_url(media, cached_only=True)
        assert "/series/tt0903747:1:1.json" in url

    def test_anime_type(self):
        client = TorrentioClient("fake_rd_key")
        media = MediaInfo(
            title="AOT", imdb_id="tt2560140", type="anime", season=1, episode=1
        )
        url = client._build_url(media, cached_only=True)
        assert "/series/" in url


# ── TorrentioClient.get_streams ───────────────────────────────────────────


@pytest.mark.asyncio
class TestGetStreams:
    async def test_returns_stream_results(self):
        client = TorrentioClient("fake_rd_key")
        client.get = AsyncMock(return_value=MagicMock(json=MagicMock(return_value={
            "streams": [
                {
                    "name": "Test.1080p",
                    "title": "👤 100 💾 2.5 GB",
                    "infoHash": "abc123",
                    "url": "https://rd.example.com/dl/cached",
                },
                {
                    "name": "Test.720p",
                    "title": "👤 50 💾 1.0 GB",
                    "infoHash": "def456",
                    "sources": ["tracker:udp://tracker1"],
                },
            ]
        })))

        media = MediaInfo(title="Test", imdb_id="tt1234567", type="movie")
        results = await client.get_streams(media)
        assert len(results) == 2
        # Cached should be first after sort
        assert results[0].is_cached_rd is True
        assert results[0].download_url == "https://rd.example.com/dl/cached"
        # Uncached should have magnet
        assert results[1].magnet is not None
        assert "btih:def456" in results[1].magnet
        await client.close()

    async def test_no_imdb_id_returns_empty(self):
        client = TorrentioClient("fake_rd_key")
        media = MediaInfo(title="Test", imdb_id=None, type="movie")
        results = await client.get_streams(media)
        assert results == []
        await client.close()

    async def test_api_failure_returns_empty(self):
        client = TorrentioClient("fake_rd_key")
        client.get = AsyncMock(side_effect=Exception("API down"))

        media = MediaInfo(title="Test", imdb_id="tt1234567", type="movie")
        results = await client.get_streams(media)
        assert results == []
        await client.close()

    async def test_empty_streams_returns_empty(self):
        client = TorrentioClient("fake_rd_key")
        client.get = AsyncMock(return_value=MagicMock(json=MagicMock(return_value={
            "streams": []
        })))

        media = MediaInfo(title="Test", imdb_id="tt1234567", type="movie")
        results = await client.get_streams(media)
        assert results == []
        await client.close()
