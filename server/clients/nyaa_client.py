"""
nyaa.si client for anime torrents.

Uses the nyaa.si RSS feed which doesn't require authentication.

Feed URL:
  https://nyaa.si/?page=rss&q={query}&c=1_2&f=0
  c=1_2  → Anime - English-translated
  f=0    → no filter (show all)

For Japanese-audio / RAW content: c=1_4 (Anime - Raw)

We query both and merge results.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from ..core.quality_scorer import ScoredStream
from .tmdb_client import MediaInfo

logger = logging.getLogger(__name__)

NYAA_RSS = "https://nyaa.si/?page=rss"

_MAX_RETRIES = 2
_RETRY_BACKOFF = 2
_NS = {"nyaa": "https://nyaa.si/xmlns/nyaa"}

_SIZE_RE = re.compile(r"([\d.]+)\s*(GiB|MiB|TiB|GB|MB|TB)", re.I)
_SEEDERS_RE = re.compile(r"<nyaa:seeders>(\d+)</nyaa:seeders>")
_HASH_RE = re.compile(r"<nyaa:infoHash>([0-9a-fA-F]+)</nyaa:infoHash>")


def _parse_size(text: str) -> Optional[int]:
    m = _SIZE_RE.search(text)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    mult = {
        "MIB": 1024**2, "MB": 1024**2,
        "GIB": 1024**3, "GB": 1024**3,
        "TIB": 1024**4, "TB": 1024**4,
    }
    return int(val * mult.get(unit, 1))


class NyaaClient:
    def __init__(self, timeout: int = 15):
        self._timeout = timeout

    async def search(self, media: MediaInfo) -> list[ScoredStream]:
        """Search nyaa.si for the given anime MediaInfo."""
        query = self._build_query(media)
        results: list[ScoredStream] = []

        for category in ("1_2", "1_4"):   # English-translated + Raw
            items = await self._fetch_rss(query, category)
            results.extend(items)

        logger.info("nyaa returned %d results for '%s'", len(results), query)
        return results

    def _build_query(self, media: MediaInfo) -> str:
        """Build a nyaa search query string."""
        parts = [media.title]
        if media.season is not None:
            parts.append(f"Season {media.season}")
        if media.episode is not None:
            parts.append(f"{media.episode:02d}")
        return " ".join(parts)

    async def _fetch_rss(self, query: str, category: str) -> list[ScoredStream]:
        url = f"{NYAA_RSS}&q={query}&c={category}&f=0"
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return self._parse_rss(resp.text)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_exc = exc
                delay = _RETRY_BACKOFF * (2 ** attempt)
                logger.info(
                    "nyaa RSS attempt %d/%d failed (cat=%s, %s) — retrying in %ds",
                    attempt + 1, _MAX_RETRIES, category, type(exc).__name__, delay,
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                logger.warning("nyaa RSS fetch failed (cat=%s): %s", category, exc)
                return []

        logger.warning(
            "nyaa RSS fetch failed after %d retries (cat=%s): %s",
            _MAX_RETRIES, category, last_exc,
        )
        return []

    def _parse_rss(self, xml_text: str) -> list[ScoredStream]:
        results: list[ScoredStream] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("nyaa RSS parse error: %s", exc)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")

            if title_el is None:
                continue

            name = title_el.text or ""
            link = link_el.text if link_el is not None else ""

            # Extract info hash
            info_hash = None
            hash_el = item.find("nyaa:infoHash", _NS)
            if hash_el is not None:
                info_hash = hash_el.text

            # Seeders
            seeders = 0
            seed_el = item.find("nyaa:seeders", _NS)
            if seed_el is not None:
                try:
                    seeders = int(seed_el.text or 0)
                except ValueError:
                    pass

            # Size
            size_bytes = None
            size_el = item.find("nyaa:size", _NS)
            if size_el is not None:
                size_bytes = _parse_size(size_el.text or "")

            # Build magnet from infoHash
            magnet = None
            if info_hash:
                magnet = f"magnet:?xt=urn:btih:{info_hash}"

            stream = ScoredStream(
                name=name,
                info_hash=info_hash,
                size_bytes=size_bytes,
                seeders=seeders,
                is_cached_rd=False,
                magnet=magnet,
            )
            results.append(stream)

        return results
