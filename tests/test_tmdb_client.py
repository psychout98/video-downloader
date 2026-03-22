"""
Unit tests for server/clients/tmdb_client.py.

Tests cover:
- MediaInfo dataclass (poster_url, display_name)
- TMDBClient._parse_query (S01E03, Season 2, S01, Episode 3, IMDb URL, trailing year)
- TMDBClient.search (multi-search, TV-specific, IMDb lookup)
- TMDBClient.get_episode_count / get_episode_title
- TMDBClient.fuzzy_resolve (typed search, multi-fallback, shortened title fallback)
- TMDBClient._build_movie_info / _build_tv_info
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")

from server.clients.tmdb_client import MediaInfo, TMDBClient


# ── MediaInfo dataclass ───────────────────────────────────────────────────


class TestMediaInfo:
    def test_poster_url_with_path(self):
        info = MediaInfo(title="Test", poster_path="/abc123.jpg")
        assert info.poster_url == "https://image.tmdb.org/t/p/w500/abc123.jpg"

    def test_poster_url_none(self):
        info = MediaInfo(title="Test", poster_path=None)
        assert info.poster_url is None

    def test_display_name_movie(self):
        info = MediaInfo(title="Inception", year=2010)
        assert info.display_name == "Inception (2010)"

    def test_display_name_movie_no_year(self):
        info = MediaInfo(title="Inception", year=None)
        assert info.display_name == "Inception"

    def test_display_name_tv_season_episode(self):
        info = MediaInfo(title="Breaking Bad", year=2008, season=1, episode=3)
        assert info.display_name == "Breaking Bad (2008) S01E03"

    def test_display_name_tv_season_only(self):
        info = MediaInfo(title="Breaking Bad", year=2008, season=2)
        assert info.display_name == "Breaking Bad (2008) Season 2"


# ── TMDBClient._parse_query ──────────────────────────────────────────────


class TestParseQuery:
    def test_s01e03(self):
        q, s, e = TMDBClient._parse_query("Breaking Bad S01E03")
        assert q == "Breaking Bad"
        assert s == 1
        assert e == 3

    def test_season_word(self):
        q, s, e = TMDBClient._parse_query("Breaking Bad Season 2")
        assert q == "Breaking Bad"
        assert s == 2
        assert e is None

    def test_s_only(self):
        q, s, e = TMDBClient._parse_query("Breaking Bad S03")
        assert q == "Breaking Bad"
        assert s == 3
        assert e is None

    def test_episode_word(self):
        q, s, e = TMDBClient._parse_query("Show Episode 5")
        assert q == "Show"
        assert e == 5

    def test_plain_query(self):
        q, s, e = TMDBClient._parse_query("Inception")
        assert q == "Inception"
        assert s is None
        assert e is None

    def test_strips_trailing_year(self):
        q, s, e = TMDBClient._parse_query("Inception 2010")
        assert q == "Inception"

    def test_strips_trailing_year_in_parens(self):
        q, s, e = TMDBClient._parse_query("Inception (2010)")
        assert q == "Inception"

    def test_imdb_url_not_stripped(self):
        # The IMDb URL is handled at search() level, not _parse_query
        q, s, e = TMDBClient._parse_query("https://www.imdb.com/title/tt1375666/")
        assert "imdb.com" in q or "tt1375666" in q


# ── TMDBClient.search ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTMDBClientSearch:
    async def test_search_movie_via_multi(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(side_effect=[
            # search/multi response
            {"results": [{
                "media_type": "movie",
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-16",
                "popularity": 50,
                "poster_path": "/abc.jpg",
            }]},
            # movie/{id}/external_ids
            {"imdb_id": "tt1375666"},
            # movie/{id} details
            {
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-16",
                "overview": "A thief...",
                "poster_path": "/abc.jpg",
                "genres": [{"id": 28, "name": "Action"}],
                "original_language": "en",
            },
        ])

        info = await client.search("Inception")
        assert info.title == "Inception"
        assert info.tmdb_id == 27205
        assert info.type == "movie"
        await client.close()

    async def test_search_tv_with_season(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(side_effect=[
            # search/tv response
            {"results": [{
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "popularity": 100,
            }]},
            # tv/{id}/external_ids
            {"imdb_id": "tt0903747"},
            # tv/{id} details
            {
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "overview": "A chemistry teacher...",
                "poster_path": "/bb.jpg",
                "genres": [{"id": 18, "name": "Drama"}],
                "origin_country": ["US"],
                "original_language": "en",
                "number_of_seasons": 5,
            },
            # tv/{id}/season/{season}
            {"episodes": [
                {"episode_number": 1, "name": "Pilot"},
                {"episode_number": 2, "name": "Cat's in the Bag..."},
            ]},
        ])

        info = await client.search("Breaking Bad S01E02")
        assert info.title == "Breaking Bad"
        assert info.season == 1
        assert info.episode == 2
        assert info.type == "tv"
        await client.close()

    async def test_search_no_results_raises(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(return_value={"results": []})

        with pytest.raises(ValueError, match="No TMDB results"):
            await client.search("xyznonexistent")
        await client.close()

    async def test_search_imdb_url(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(side_effect=[
            # find/{imdb_id}
            {"movie_results": [{
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-16",
                "popularity": 50,
            }], "tv_results": []},
            # movie/{id}/external_ids
            {"imdb_id": "tt1375666"},
            # movie/{id} details
            {
                "id": 27205, "title": "Inception", "release_date": "2010-07-16",
                "overview": "...", "poster_path": "/abc.jpg",
                "genres": [], "original_language": "en",
            },
        ])

        info = await client.search("https://www.imdb.com/title/tt1375666/")
        assert info.tmdb_id == 27205
        await client.close()


# ── TMDBClient.get_episode_count / get_episode_title ──────────────────────


@pytest.mark.asyncio
class TestTMDBClientEpisodeLookup:
    async def test_get_episode_count(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(return_value={
            "episodes": [{"episode_number": 1}, {"episode_number": 2}, {"episode_number": 3}]
        })
        count = await client.get_episode_count(1396, 1)
        assert count == 3
        await client.close()

    async def test_get_episode_count_failure(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(side_effect=Exception("API error"))
        count = await client.get_episode_count(1396, 1)
        assert count == 0
        await client.close()

    async def test_get_episode_title(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(return_value={"name": "Pilot"})
        title = await client.get_episode_title(1396, 1, 1)
        assert title == "Pilot"
        await client.close()

    async def test_get_episode_title_failure(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(side_effect=Exception("API error"))
        title = await client.get_episode_title(1396, 1, 1)
        assert title == ""
        await client.close()


# ── TMDBClient.fuzzy_resolve ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestTMDBClientFuzzyResolve:
    async def test_fuzzy_resolve_typed_search_hit(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(return_value={
            "results": [{
                "title": "Inception",
                "release_date": "2010-07-16",
                "poster_path": "/abc.jpg",
                "popularity": 50,
            }]
        })
        title, year, poster = await client.fuzzy_resolve("Inception", "movie", 2010)
        assert title == "Inception"
        assert year == 2010
        assert poster == "/abc.jpg"
        await client.close()

    async def test_fuzzy_resolve_multi_fallback(self):
        client = TMDBClient("fake_key")
        # Typed search returns nothing, multi returns a result
        client._get = AsyncMock(side_effect=[
            {"results": []},  # typed with year
            {"results": []},  # typed without year
            {"results": [{
                "media_type": "movie",
                "title": "Inception",
                "release_date": "2010-07-16",
                "poster_path": "/abc.jpg",
                "popularity": 50,
            }]},
        ])
        title, year, poster = await client.fuzzy_resolve("Inception", "movie")
        assert title == "Inception"
        await client.close()

    async def test_fuzzy_resolve_no_results_raises(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(return_value={"results": []})

        with pytest.raises(ValueError, match="No TMDB results"):
            await client.fuzzy_resolve("x y", "movie")
        await client.close()

    async def test_fuzzy_resolve_shortened_title_fallback(self):
        client = TMDBClient("fake_key")
        client._get = AsyncMock(side_effect=[
            {"results": []},  # typed with year
            {"results": []},  # typed without year
            {"results": []},  # multi full title
            {"results": [{  # multi shortened title
                "media_type": "movie",
                "title": "Demon Slayer",
                "release_date": "2025-01-01",
                "poster_path": "/ds.jpg",
                "popularity": 80,
            }]},
        ])
        title, year, poster = await client.fuzzy_resolve(
            "Demon Slayer Kimetsu no Yaiba Infinity Castle", "movie"
        )
        assert title == "Demon Slayer"
        await client.close()
