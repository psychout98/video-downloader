"""
Real-Debrid API client.

Relevant endpoints used
-----------------------
POST /torrents/addMagnet          → add a magnet to RD; returns torrent id
POST /torrents/selectFiles/{id}   → select all files for download
GET  /torrents/info/{id}          → poll status; when "downloaded" fetch links[]
POST /unrestrict/link             → convert an RD link to a direct CDN URL
GET  /torrents/instantAvailability/{hash}  → check cache before adding

Real-Debrid base URL: https://api.real-debrid.com/rest/1.0
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_BACKOFF = 2

RD_BASE = "https://api.real-debrid.com/rest/1.0"

# Torrent statuses considered "done" on RD's side
_DONE_STATUSES = {"downloaded", "magnet_done"}
_ERROR_STATUSES = {"error", "virus", "dead", "magnet_error"}


class RealDebridError(Exception):
    pass


class RealDebridClient:
    def __init__(self, api_key: str, poll_interval: int = 30):
        self._key = api_key
        self._poll_interval = poll_interval
        self._client = httpx.AsyncClient(
            base_url=RD_BASE,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Cache check
    # ------------------------------------------------------------------

    async def is_cached(self, info_hash: str) -> bool:
        """Return True if the torrent hash is instantly available on RD.

        Retries on transient connection errors so a single network hiccup
        doesn't cause every hash to look uncached.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES):
            try:
                r = await self._client.get(
                    f"/torrents/instantAvailability/{info_hash.lower()}"
                )
                r.raise_for_status()
                data = r.json()
                entry = data.get(info_hash.lower(), {})
                return bool(entry.get("rd"))
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_exc = exc
                delay = _RETRY_BACKOFF * (2 ** attempt)
                logger.info(
                    "RD cache check attempt %d/%d failed (%s) — retrying in %ds",
                    attempt + 1, _MAX_RETRIES, type(exc).__name__, delay,
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                logger.warning("RD cache check failed: %s", exc)
                return False

        logger.warning("RD cache check failed after %d retries: %s", _MAX_RETRIES, last_exc)
        return False

    # ------------------------------------------------------------------
    # Add magnet
    # ------------------------------------------------------------------

    async def add_magnet(self, magnet: str) -> str:
        """Add *magnet* to RD and return the RD torrent ID."""
        r = await self._client.post("/torrents/addMagnet", data={"magnet": magnet})
        if r.status_code not in (200, 201):
            raise RealDebridError(f"addMagnet failed ({r.status_code}): {r.text}")
        data = r.json()
        torrent_id = data.get("id")
        if not torrent_id:
            raise RealDebridError(f"addMagnet returned no id: {data}")
        logger.info("RD torrent added: %s", torrent_id)
        return torrent_id

    # ------------------------------------------------------------------
    # Select files
    # ------------------------------------------------------------------

    async def select_all_files(self, torrent_id: str) -> None:
        """Tell RD to download all files in the torrent."""
        r = await self._client.post(
            f"/torrents/selectFiles/{torrent_id}",
            data={"files": "all"},
        )
        if r.status_code not in (200, 201, 204):
            raise RealDebridError(
                f"selectFiles failed ({r.status_code}): {r.text}"
            )

    # ------------------------------------------------------------------
    # Poll until downloaded
    # ------------------------------------------------------------------

    async def wait_until_downloaded(
        self,
        torrent_id: str,
        on_progress=None,   # optional async callable(percent: int)
    ) -> list[str]:
        """
        Poll the RD torrent info endpoint until the torrent is downloaded.
        Returns the list of RD download links.
        """
        while True:
            info = await self.get_torrent_info(torrent_id)
            status = info.get("status", "")
            progress = info.get("progress", 0)

            logger.debug("RD torrent %s status=%s progress=%s%%", torrent_id, status, progress)

            if on_progress:
                await on_progress(int(progress))

            if status in _DONE_STATUSES:
                links = info.get("links", [])
                if not links:
                    raise RealDebridError("Torrent downloaded but no links returned")
                return links

            if status in _ERROR_STATUSES:
                raise RealDebridError(f"RD torrent failed with status: {status}")

            await asyncio.sleep(self._poll_interval)

    async def get_torrent_info(self, torrent_id: str) -> dict:
        r = await self._client.get(f"/torrents/info/{torrent_id}")
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Unrestrict link → direct CDN download URL
    # ------------------------------------------------------------------

    async def unrestrict_link(self, link: str) -> tuple[str, Optional[int]]:
        """
        Convert an RD link to a direct CDN download URL.
        Returns (download_url, filesize_bytes).
        """
        r = await self._client.post("/unrestrict/link", data={"link": link})
        if r.status_code not in (200, 201):
            raise RealDebridError(f"unrestrict/link failed ({r.status_code}): {r.text}")
        data = r.json()
        url = data.get("download") or data.get("url")
        size = data.get("filesize")
        if not url:
            raise RealDebridError(f"unrestrict/link returned no URL: {data}")
        return url, size

    async def unrestrict_all(self, links: list[str]) -> list[tuple[str, Optional[int]]]:
        """Unrestrict a list of RD links concurrently."""
        tasks = [self.unrestrict_link(link) for link in links]
        return list(await asyncio.gather(*tasks))

    # ------------------------------------------------------------------
    # High-level: add + select + wait + unrestrict in one call
    # ------------------------------------------------------------------

    async def download_magnet(
        self, magnet: str, on_progress=None
    ) -> tuple[list[tuple[str, Optional[int]]], str]:
        """
        Full pipeline for a non-cached magnet:
          1. Add to RD
          2. Select all files
          3. Poll until downloaded
          4. Unrestrict all links
        Returns (list_of_(cdn_url, file_size_bytes), torrent_id).
        """
        torrent_id = await self.add_magnet(magnet)
        await self.select_all_files(torrent_id)
        rd_links = await self.wait_until_downloaded(torrent_id, on_progress=on_progress)
        unrestricted = await self.unrestrict_all(rd_links)
        return unrestricted, torrent_id
