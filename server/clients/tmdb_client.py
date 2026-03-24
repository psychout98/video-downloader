"""
TMDB client — parses free-text queries and resolves them to structured media info.

Query parsing examples
----------------------
"Inception"                  → movie search
"Breaking Bad"               → tv search
"Breaking Bad S01"           → tv, season=1
"Breaking Bad S01E03"        → tv, season=1, episode=3
"Breaking Bad season 2"      → tv, season=2
"Attack on Titan"            → anime (auto-detected via TMDB genres)
"https://www.imdb.com/title/tt1630029/"  → direct IMDb lookup
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3/"

# Anime detection: TMDB genre id 16 = Animation; we also check origin_country.
ANIME_KEYWORDS = re.compile(
    r"\b(anime|manga|ova|ona|shounen|shonen|shoujo|seinen|isekai|mecha)\b", re.I
)

# Season/episode patterns
_SE_FULL = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")   # S01E03
_S_ONLY = re.compile(r"[Ss](\d{1,2})\b")                # S01
_SEASON_WORD = re.compile(r"\bseason\s+(\d{1,2})\b", re.I)
_EPISODE_WORD = re.compile(r"\bepisode\s+(\d{1,3})\b", re.I)
_IMDB_URL = re.compile(r"imdb\.com/title/(tt\d+)")
_YEAR_TRAIL = re.compile(r"\s*\(?(19|20)\d{2}\)?$")


@dataclass
class MediaInfo:
    title: str
    year: Optional[int] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    type: str = "movie"          # "movie" | "tv" | "anime"
    season: Optional[int] = None
    episode: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None   # e.g. "/abc123.jpg" — combine with TMDB image base
    # TV details
    total_seasons: Optional[int] = None
    episodes_in_season: Optional[int] = None   # populated if season is set
    episode_titles: dict[int, str] = field(default_factory=dict)  # {ep_num: title}
    # Anime flag separate from type so we can still distinguish
    is_anime: bool = False

    @property
    def poster_url(self) -> Optional[str]:
        """Full TMDB poster URL at w500 size, or None."""
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w500{self.poster_path}"
        return None

    @property
    def display_name(self) -> str:
        base = f"{self.title} ({self.year})" if self.year else self.title
        if self.season and self.episode:
            return f"{base} S{self.season:02d}E{self.episode:02d}"
        if self.season:
            return f"{base} Season {self.season}"
        return base


class TMDBClient(BaseAPIClient):
    def __init__(self, api_key: str):
        super().__init__(
            base_url=TMDB_BASE,
            timeout=15,
            max_retries=3,
            backoff_base=1.0,
            params={"api_key": api_key},
        )
        self._key = api_key

    async def _get(self, path: str, **kwargs) -> dict:
        """GET a TMDB endpoint and return parsed JSON.

        Strips leading "/" so httpx resolves relative to base_url
        (a leading "/" would discard the /3/ path component per RFC 3986).
        """
        path = path.lstrip("/")
        r = await self.get(path, **kwargs)
        return r.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, raw_query: str) -> MediaInfo:
        """Parse *raw_query* and resolve it to a fully-populated MediaInfo."""
        query, season, episode = self._parse_query(raw_query.strip())

        # Direct IMDb URL?
        imdb_match = _IMDB_URL.search(raw_query)
        if imdb_match:
            return await self._lookup_imdb(imdb_match.group(1), season, episode)

        # Try movie first if no season/episode hints; otherwise favour TV
        if season is not None or episode is not None:
            info = await self._search_tv(query, season, episode)
        else:
            # Try multi-search and pick highest-confidence result
            info = await self._search_multi(query, season, episode)

        return info

    async def get_episode_count(self, tmdb_id: int, season: int) -> int:
        """Return the number of episodes in a given TV season."""
        try:
            data = await self._get(f"tv/{tmdb_id}/season/{season}")
            return len(data.get("episodes", []))
        except Exception as exc:
            logger.warning("get_episode_count failed (tmdb=%d, s=%d): %s", tmdb_id, season, exc)
            return 0

    async def get_episode_title(self, tmdb_id: int, season: int, episode: int) -> str:
        try:
            data = await self._get(f"tv/{tmdb_id}/season/{season}/episode/{episode}")
            return data.get("name", "")
        except Exception as exc:
            logger.warning("get_episode_title failed (tmdb=%d, s=%d, e=%d): %s", tmdb_id, season, episode, exc)
            return ""

    async def fuzzy_resolve(
        self,
        title: str,
        media_type: str = "movie",
        year: Optional[int] = None,
    ) -> tuple[str, Optional[int], Optional[str]]:
        """Find the best TMDB match for a title using progressive fallback.

        Returns ``(canonical_title, canonical_year, poster_path)`` where
        ``poster_path`` is the raw TMDB path (e.g. ``"/abc123.jpg"``).

        Search strategy (stops at the first pass that returns results):
          1. Type-specific endpoint  + year filter
          2. Type-specific endpoint  (no year)
          3. ``/search/multi``       with full title   (TMDB's own fuzzy engine)
          4. ``/search/multi``       progressively shorter title (strips trailing
             words one at a time, up to 4 removals, stops at 2-word minimum)

        Results are scored by (exact-title-and-year, exact-title, popularity)
        so a precise match always wins even if found during a fuzzy pass.
        """
        is_tv     = media_type in ("tv", "anime")
        endpoint  = "search/tv" if is_tv else "search/movie"
        date_key  = "first_air_date_year" if is_tv else "year"
        title_key = "name" if is_tv else "title"

        def _score(item: dict) -> tuple:
            t  = (item.get("title") or item.get("name") or "").lower()
            ds = item.get("release_date") or item.get("first_air_date") or ""
            iy = int(ds[:4]) if ds[:4].isdigit() else 0
            return (
                t == title.lower() and (iy == year if year else True),
                t == title.lower(),
                item.get("popularity", 0),
            )

        def _extract(best: dict, tkey: str) -> tuple[str, Optional[int], Optional[str]]:
            ds = best.get("release_date") or best.get("first_air_date") or ""
            return (
                best.get(tkey) or title,
                int(ds[:4]) if ds[:4].isdigit() else year,
                best.get("poster_path"),
            )

        async def _typed(q: str, with_year: bool) -> list[dict]:
            p: dict = {"query": q, "include_adult": False}
            if with_year and year:
                p[date_key] = year
            data = await self._get(endpoint, params=p)
            return data.get("results", [])

        async def _multi(q: str) -> list[dict]:
            data = await self._get(
                "search/multi", params={"query": q, "include_adult": False}
            )
            return [
                x for x in data.get("results", [])
                if x.get("media_type") in ("movie", "tv")
            ]

        # Attempt 1 & 2 — type-specific, with then without year
        for with_year in (True, False):
            results = await _typed(title, with_year)
            if results:
                results.sort(key=_score, reverse=True)
                return _extract(results[0], title_key)

        # Attempt 3 — TMDB multi-search (handles cross-type and fuzzy spelling)
        results = await _multi(title)
        if results:
            results.sort(key=_score, reverse=True)
            best  = results[0]
            tkey  = "name" if best.get("media_type") == "tv" else "title"
            return _extract(best, tkey)

        # Attempt 4 — progressively shorten the title (handles over-long
        # filenames like "Demon.Slayer.Kimetsu.no.Yaiba.Infinity.Castle.2025")
        words = title.split()
        for drop in range(1, min(5, len(words) - 1)):   # keep at least 2 words
            shorter  = " ".join(words[:-drop])
            results  = await _multi(shorter)
            if results:
                results.sort(key=_score, reverse=True)
                best  = results[0]
                tkey  = "name" if best.get("media_type") == "tv" else "title"
                logger.info(
                    "fuzzy_resolve: matched '%s' via shortened query '%s'",
                    best.get(tkey), shorter,
                )
                return _extract(best, tkey)

        raise ValueError(f"No TMDB results for '{title}'")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_query(query: str) -> tuple[str, Optional[int], Optional[int]]:
        """Strip season/episode tags from *query* and return them separately."""
        season = episode = None

        # S01E03 style
        m = _SE_FULL.search(query)
        if m:
            season, episode = int(m.group(1)), int(m.group(2))
            query = query[:m.start()].strip()
            return query, season, episode

        # "Season 2" / "season 2"
        m = _SEASON_WORD.search(query)
        if m:
            season = int(m.group(1))
            query = query[:m.start()].strip()

        # S01 style
        if season is None:
            m = _S_ONLY.search(query)
            if m:
                season = int(m.group(1))
                query = query[:m.start()].strip()

        # "Episode 3"
        m = _EPISODE_WORD.search(query)
        if m:
            episode = int(m.group(1))
            query = query[:m.start()].strip()

        # Strip trailing year from clean query
        query = _YEAR_TRAIL.sub("", query).strip()
        return query, season, episode

    async def _search_multi(
        self, query: str, season: Optional[int], episode: Optional[int]
    ) -> MediaInfo:
        """Use TMDB's /search/multi and pick movie vs TV based on result confidence."""
        data = await self._get("search/multi", params={"query": query, "include_adult": False})
        results = data.get("results", [])

        # Filter to movie/tv, sort by popularity
        candidates = [x for x in results if x.get("media_type") in ("movie", "tv")]
        if not candidates:
            raise ValueError(f"No TMDB results for '{query}'")

        candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        best = candidates[0]
        media_type = best["media_type"]

        if media_type == "movie":
            return await self._build_movie_info(best)
        else:
            return await self._build_tv_info(best, season, episode)

    async def _search_tv(
        self, query: str, season: Optional[int], episode: Optional[int]
    ) -> MediaInfo:
        data = await self._get("search/tv", params={"query": query})
        results = data.get("results", [])
        if not results:
            raise ValueError(f"No TV show found for '{query}'")
        results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        return await self._build_tv_info(results[0], season, episode)

    async def _lookup_imdb(
        self, imdb_id: str, season: Optional[int], episode: Optional[int]
    ) -> MediaInfo:
        data = await self._get("find/" + imdb_id, params={"external_source": "imdb_id"})
        if data.get("movie_results"):
            return await self._build_movie_info(data["movie_results"][0])
        if data.get("tv_results"):
            return await self._build_tv_info(data["tv_results"][0], season, episode)
        raise ValueError(f"IMDb ID {imdb_id} not found on TMDB")

    async def _build_movie_info(self, tmdb_result: dict) -> MediaInfo:
        tmdb_id = tmdb_result["id"]

        # Fetch external IDs for IMDb
        ext = await self._get(f"movie/{tmdb_id}/external_ids")
        imdb_id = ext.get("imdb_id", "")

        # Fetch full movie details for genres
        details = await self._get(f"movie/{tmdb_id}")

        title = details.get("title") or tmdb_result.get("title", "Unknown")
        year_str = (details.get("release_date") or "")[:4]
        year = int(year_str) if year_str.isdigit() else None
        genres = [g["id"] for g in details.get("genres", [])]
        is_anime = 16 in genres and details.get("original_language") == "ja"

        return MediaInfo(
            title=title,
            year=year,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            type="anime" if is_anime else "movie",
            is_anime=is_anime,
            overview=details.get("overview", ""),
            poster_path=details.get("poster_path") or tmdb_result.get("poster_path"),
        )

    async def _build_tv_info(
        self,
        tmdb_result: dict,
        season: Optional[int],
        episode: Optional[int],
    ) -> MediaInfo:
        tmdb_id = tmdb_result["id"]

        ext = await self._get(f"tv/{tmdb_id}/external_ids")
        imdb_id = ext.get("imdb_id", "")

        details = await self._get(f"tv/{tmdb_id}")

        title = details.get("name") or tmdb_result.get("name", "Unknown")
        year_str = (details.get("first_air_date") or "")[:4]
        year = int(year_str) if year_str.isdigit() else None
        genres = [g["id"] for g in details.get("genres", [])]
        origin = details.get("origin_country", [])
        is_anime = (
            16 in genres
            and (details.get("original_language") == "ja" or "JP" in origin)
        ) or ANIME_KEYWORDS.search(title) is not None

        total_seasons = details.get("number_of_seasons")
        media_type = "anime" if is_anime else "tv"

        # If a season was requested, fetch its episode list
        ep_count = 0
        ep_titles: dict[int, str] = {}
        if season is not None:
            try:
                s_data = await self._get(f"tv/{tmdb_id}/season/{season}")
                episodes = s_data.get("episodes", [])
                ep_count = len(episodes)
                ep_titles = {e["episode_number"]: e.get("name", "") for e in episodes}
            except Exception as exc:
                logger.warning("Failed to fetch season %d for tmdb=%d: %s", season, tmdb_id, exc)

        return MediaInfo(
            title=title,
            year=year,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            type=media_type,
            season=season,
            episode=episode,
            total_seasons=total_seasons,
            episodes_in_season=ep_count or None,
            episode_titles=ep_titles,
            is_anime=is_anime,
            overview=details.get("overview", ""),
            poster_path=details.get("poster_path") or tmdb_result.get("poster_path"),
        )
