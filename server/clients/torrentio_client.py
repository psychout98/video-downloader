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

import asyncio
import logging
import re
from typing import Optional

import httpx

from ..core.quality_scorer import ScoredStream
from .tmdb_client import MediaInfo

logger = logging.getLogger(__name__)

TORRENTIO_BASE = "https://torrentio.strem.fun"

# Retry config for transient network errors (ConnectError, timeouts, 5xx)
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2          # seconds; doubles each attempt
_RETRYABLE_STATUS = {502, 503, 504, 520, 521, 522, 524}

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

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, */*",
    }

    async def _fetch_with_retry(self, url: str) -> Optional[dict]:
        """GET *url* with retry + exponential backoff on transient errors.

        Returns the parsed JSON dict on success, or ``None`` if all retries
        are exhausted.  Re-raises ``httpx.HTTPStatusError`` for non-retryable
        HTTP errors (e.g. 403) so the caller can surface them to the user.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, headers=self._HEADERS)
                    if resp.status_code in _RETRYABLE_STATUS:
                        raise httpx.HTTPStatusError(
                            f"Retryable {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    raise  # 4xx (e.g. 403) — not transient, surface immediately
                last_exc = exc
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_exc = exc
            except Exception as exc:
                # Unexpected error — log and bail without retry
                logger.warning(
                    "Torrentio request failed (%s): %r",
                    type(exc).__name__, exc,
                )
                return None

            delay = _RETRY_BACKOFF * (2 ** attempt)
            logger.info(
                "Torrentio attempt %d/%d failed (%s) — retrying in %ds",
                attempt + 1, _MAX_RETRIES, type(last_exc).__name__, delay,
            )
            await asyncio.sleep(delay)

        logger.warning(
            "Torrentio request failed after %d retries: %r",
            _MAX_RETRIES, last_exc,
        )
        return None

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

        Retries up to ``_MAX_RETRIES`` times on transient network errors
        (ConnectError, timeouts, 5xx) with exponential backoff.
        """
        if not media.imdb_id:
            logger.warning("No IMDb ID — cannot query Torrentio")
            return []

        url = self._build_url(media, cached_only)
        logger.debug("Torrentio URL: %s", url)

        data = await self._fetch_with_retry(url)
        if data is None:
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
                magnet=magnet,
                file_idx=file_idx,
            )
            results.append(stream)

        logger.info(
            "Torrentio returned %d streams for %s (cached_only=%s)",
            len(results), media.display_name, cached_only,
        )
        return results
