"""
Torrentio client — aggregates torrents from many indexers via the Torrentio
Stremio addon API, optionally filtered to Real-Debrid cached content only.

Torrentio URL format
--------------------
  https://torrentio.strem.fun/{options}/stream/{type}/{id}.json

With RD (returns only cached items with direct download URLs):
  options = "realdebrid={API_KEY}|sort=qualitysize"

Without RD (returns all torrents with info_hash for manual RD addition):
  options = "sort=qualitysize"

Stream types:
  movie  → id = IMDb ID  (e.g. tt1375666)
  series → id = {imdb_id}:{season}:{episode}  (e.g. tt0903747:1:1)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

from ..core.quality_scorer import ScoredStream
from .tmdb_client import MediaInfo

logger = logging.getLogger(__name__)

TORRENTIO_BASE = "https://torrentio.strem.fun"

# Parse seeder count from Torrentio title strings like "👤 842 💾 52.3 GB"
_SEEDERS_RE = re.compile(r"👤\s*(\d+)")
_SIZE_RE = re.compile(r"💾\s*([\d.]+)\s*(GB|MB|TB)", re.I)


def _parse_size(title_text: str) -> Optional[int]:
    m = _SIZE_RE.search(title_text)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    multipliers = {"MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(val * multipliers.get(unit, 1))


def _parse_seeders(title_text: str) -> int:
    m = _SEEDERS_RE.search(title_text)
    return int(m.group(1)) if m else 0


class TorrentioClient:
    def __init__(self, rd_api_key: str, timeout: int = 20):
        self._rd_key = rd_api_key
        self._timeout = timeout

    def _build_url(self, media: MediaInfo, cached_only: bool) -> str:
        if cached_only and self._rd_key:
            options = f"realdebrid={self._rd_key}|sort=qualitysize|limit=20"
        else:
            options = "sort=qualitysize|limit=20"

        if media.type in ("tv", "anime") and media.season is not None:
            ep = media.episode or 1
            stream_id = f"{media.imdb_id}:{media.season}:{ep}"
            stream_type = "series"
        else:
            stream_id = media.imdb_id
            stream_type = "movie"

        return f"{TORRENTIO_BASE}/{options}/stream/{stream_type}/{stream_id}.json"

    async def get_streams(
        self, media: MediaInfo, cached_only: bool = True
    ) -> list[ScoredStream]:
        """
        Fetch streams from Torrentio.

        If *cached_only* is True the results are filtered to Real-Debrid cached
        content and each stream includes a *download_url* field.

        If *cached_only* is False we return raw infoHash results that can be
        added to RD manually (slower, but still possible).
        """
        if not media.imdb_id:
            logger.warning("No IMDb ID — cannot query Torrentio")
            return []

        url = self._build_url(media, cached_only)
        logger.debug("Torrentio URL: %s", url)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, */*",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError:
            # HTTP 4xx/5xx — re-raise so the caller can show a meaningful error
            # (e.g. 403 means the Real-Debrid API key is invalid or expired)
            raise
        except Exception as exc:
            logger.warning("Torrentio request failed (%s): %r", type(exc).__name__, exc)
            return []

        streams = data.get("streams", [])
        results: list[ScoredStream] = []

        for s in streams:
            name = s.get("name", "")
            title = s.get("title", "")
            info_hash = s.get("infoHash") or s.get("infoHashes", [None])[0]
            download_url = s.get("url")   # Only present when RD-filtered
            file_idx = s.get("fileIdx")

            # Build magnet if we have a hash but no URL
            magnet = None
            if info_hash and not download_url:
                tracker_list = s.get("sources", [])
                trackers = "&".join(
                    f"tr={t.replace('tracker:', '')}"
                    for t in tracker_list
                    if t.startswith("tracker:")
                )
                magnet = f"magnet:?xt=urn:btih:{info_hash}&{trackers}" if trackers else \
                         f"magnet:?xt=urn:btih:{info_hash}"

            # Combine name + title for quality scoring
            combined = f"{name} {title}"

            stream = ScoredStream(
                name=combined,
                info_hash=info_hash,
                download_url=download_url,
                size_bytes=_parse_size(title),
                seeders=_parse_seeders(title),
                is_cached_rd=bool(download_url),
            )
            # Attach the magnet as a custom attribute for the RD client
            stream._magnet = magnet  # type: ignore[attr-defined]
            stream._file_idx = file_idx  # type: ignore[attr-defined]
            results.append(stream)

        logger.info(
            "Torrentio returned %d streams for %s (cached_only=%s)",
            len(results), media.display_name, cached_only,
        )
        return results
