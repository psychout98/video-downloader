"""
Background job processor.

Architecture
------------
- A single JobProcessor instance is created at app startup.
- A polling loop runs every POLL_INTERVAL seconds and picks up PENDING jobs.
- Each job is processed with a semaphore (MAX_CONCURRENT_DOWNLOADS).
- The full pipeline per job:
    1. TMDB search  -> resolve title / IMDb ID / type
    2. Torrentio (RD-cached) -> get streams with direct CDN URLs
       fallback: Torrentio (all) + manual RD add + wait + unrestrict
       anime bonus: nyaa.si query
    3. Quality scoring -> pick best stream
    4. Resolve all RD download URLs (season packs get every episode file)
    5. Download to staging area (streamed, chunked, with progress)
    6. Organise into library (Plex-compatible naming)
    7. Download TMDB poster into the show/movie folder
    8. Mark COMPLETE
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Optional

import aiofiles
import httpx

from ..config import settings
from ..database import (
    JobStatus,
    append_log,
    get_job,
    get_pending_jobs,
    update_job,
)
from .media_organizer import MediaOrganizer
from ..clients.nyaa_client import NyaaClient
from .quality_scorer import QualityScorer, ScoredStream
from ..clients.realdebrid_client import RealDebridClient, RealDebridError
from ..clients.tmdb_client import MediaInfo, TMDBClient
from ..clients.torrentio_client import TorrentioClient

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5   # seconds between queue polls

# Video file extensions used when filtering RD links for season packs
_VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"}


class JobProcessor:
    def __init__(self):
        self._sem = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
        self._active: dict[str, asyncio.Task] = {}
        self._running = False

        self._tmdb = TMDBClient(settings.TMDB_API_KEY)
        self._torrentio = TorrentioClient(settings.REAL_DEBRID_API_KEY)
        self._nyaa = NyaaClient()
        self._rd = RealDebridClient(
            settings.REAL_DEBRID_API_KEY, poll_interval=settings.RD_POLL_INTERVAL
        )
        self._scorer = QualityScorer()
        self._organizer = MediaOrganizer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        asyncio.create_task(self._poll_loop())
        logger.info("JobProcessor started")

    def stop(self):
        self._running = False
        logger.info("JobProcessor stopping -- %d active jobs", len(self._active))

    def cancel_job(self, job_id: str) -> bool:
        task = self._active.get(job_id)
        if task:
            task.cancel()
            return True
        return False

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self):
        while self._running:
            try:
                pending = await get_pending_jobs()
                for job in pending:
                    jid = job["id"]
                    if jid not in self._active:
                        task = asyncio.create_task(self._process(jid))
                        self._active[jid] = task
                        task.add_done_callback(lambda t, j=jid: self._active.pop(j, None))
            except Exception:
                logger.exception("Error in job poll loop")
            await asyncio.sleep(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Pipeline entry
    # ------------------------------------------------------------------

    async def _process(self, job_id: str):
        async with self._sem:
            try:
                await self._run_pipeline(job_id)
            except asyncio.CancelledError:
                await update_job(job_id, status=JobStatus.CANCELLED)
                await _log(job_id, "Job cancelled")
                logger.info("Job %s cancelled", job_id)
            except Exception as exc:
                logger.exception("Job %s failed: %s", job_id, exc)
                await update_job(job_id, status=JobStatus.FAILED, error=str(exc))
                await _log(job_id, f"ERROR: {exc}")

    async def _run_pipeline(self, job_id: str):
        import json as _json
        job = await get_job(job_id)
        if not job:
            return

        query = job["query"]
        await _log(job_id, f"Starting: {query!r}")

        # Fast path: user pre-selected a stream from the UI
        if job.get("stream_data"):
            await self._run_preselected_pipeline(job_id, job)
            return

        # 1. TMDB search
        await update_job(job_id, status=JobStatus.SEARCHING)
        await _log(job_id, "Searching TMDB ...")
        try:
            media = await self._tmdb.search(query)
        except Exception as exc:
            raise ValueError(f"TMDB search failed: {exc}") from exc

        await update_job(
            job_id,
            title=media.title,
            year=media.year,
            imdb_id=media.imdb_id,
            type=media.type,
            season=media.season,
            episode=media.episode,
            status=JobStatus.FOUND,
        )
        await _log(job_id, f"Found: {media.display_name} [{media.type}] IMDb={media.imdb_id}")

        # 2. Collect streams
        streams: list[ScoredStream] = []

        if media.is_anime:
            await _log(job_id, "Querying nyaa.si ...")
            nyaa_streams = await self._nyaa.search(media)
            for s in nyaa_streams:
                if s.info_hash and await self._rd.is_cached(s.info_hash):
                    s.is_cached_rd = True
                    streams.append(s)
            await _log(job_id, f"nyaa cached: {len(streams)} result(s)")

        await _log(job_id, "Querying Torrentio (RD cache) ...")
        cached_streams = await self._torrentio.get_streams(media, cached_only=True)
        streams.extend(cached_streams)
        await _log(job_id, f"Torrentio cached: {len(cached_streams)} result(s)")

        if not streams:
            await _log(job_id, "No cached results -- querying Torrentio (all) ...")
            all_streams = await self._torrentio.get_streams(media, cached_only=False)
            streams.extend(all_streams)
            await _log(job_id, f"Torrentio (all): {len(all_streams)} result(s)")

        if not streams:
            raise ValueError(f"No torrents found for {media.display_name!r}")

        # 3. Score and pick best
        ranked = self._scorer.rank(streams)
        best = ranked[0]
        await _log(
            job_id,
            f"Best: {best.name[:80]} | score={best.score} | {best.quality_str}"
            + (f" | {best.size_bytes // 1024**3:.1f} GB" if best.size_bytes else ""),
        )
        await update_job(job_id, quality=best.quality_str, torrent_name=best.name[:120])

        # 4. Resolve download files via RD
        download_files = await self._resolve_rd_files(job_id, best, media)

        # 5+6+7. Download, organise, save poster
        staging_dir = Path(settings.DOWNLOADS_DIR)
        staging_dir.mkdir(parents=True, exist_ok=True)
        await self._download_and_organize(job_id, download_files, media, best, staging_dir)

    # ------------------------------------------------------------------
    # Pre-selected stream fast path
    # ------------------------------------------------------------------

    async def _run_preselected_pipeline(self, job_id: str, job: dict):
        import json as _json

        sd = _json.loads(job["stream_data"])
        media_d = sd["media"]
        stream_d = sd["stream"]

        media = MediaInfo(
            title=media_d["title"],
            year=media_d.get("year"),
            imdb_id=media_d.get("imdb_id"),
            tmdb_id=media_d.get("tmdb_id"),
            type=media_d.get("type", "movie"),
            season=media_d.get("season"),
            episode=media_d.get("episode"),
            is_anime=media_d.get("is_anime", False),
            episode_titles=media_d.get("episode_titles", {}),
            poster_path=media_d.get("poster_path"),
        )

        best = ScoredStream(
            name=stream_d["name"],
            info_hash=stream_d.get("info_hash"),
            download_url=stream_d.get("download_url"),
            size_bytes=stream_d.get("size_bytes"),
            seeders=stream_d.get("seeders", 0),
            is_cached_rd=stream_d.get("is_cached_rd", False),
            quality_str=stream_d.get("quality_str", ""),
            score=stream_d.get("score", 0),
        )
        best._magnet = stream_d.get("magnet")  # type: ignore[attr-defined]
        best._file_idx = stream_d.get("file_idx")  # type: ignore[attr-defined]

        await update_job(
            job_id,
            title=media.title, year=media.year, imdb_id=media.imdb_id,
            type=media.type, season=media.season, episode=media.episode,
            quality=best.quality_str, torrent_name=best.name[:120],
            status=JobStatus.FOUND,
        )
        await _log(job_id, f"Pre-selected stream: {best.name[:80]}")
        await _log(job_id, f"Quality: {best.quality_str} | Score: {best.score}")

        download_files = await self._resolve_rd_files(job_id, best, media)

        staging_dir = Path(settings.DOWNLOADS_DIR)
        staging_dir.mkdir(parents=True, exist_ok=True)
        await self._download_and_organize(job_id, download_files, media, best, staging_dir)

    # ------------------------------------------------------------------
    # Shared: resolve RD download URLs
    # ------------------------------------------------------------------

    async def _resolve_rd_files(
        self, job_id: str, best: ScoredStream, media: MediaInfo
    ) -> list[tuple[str, Optional[int]]]:
        """
        Return list of (cdn_url, size_bytes) to download.
        - Single episode/movie: one entry (uses Torrentio direct URL if cached)
        - Season pack (TV/anime, no specific episode): ALL video files in torrent
        """
        is_season_pack = media.type in ("tv", "anime") and media.episode is None

        if best.is_cached_rd and best.download_url and not is_season_pack:
            await _log(job_id, "Using pre-resolved RD URL (instant cache)")
            return [(best.download_url, best.size_bytes)]

        # Go through RD API to get all file links
        magnet = getattr(best, "_magnet", None)
        if not magnet and best.info_hash:
            magnet = f"magnet:?xt=urn:btih:{best.info_hash}"
        if not magnet:
            raise ValueError("No magnet link available for this stream")

        await update_job(job_id, status=JobStatus.ADDING_TO_RD)
        await _log(job_id, "Adding to Real-Debrid ...")
        torrent_id = await self._rd.add_magnet(magnet)
        await self._rd.select_all_files(torrent_id)
        await update_job(job_id, rd_torrent_id=torrent_id, status=JobStatus.WAITING_FOR_RD)
        await _log(job_id, f"Waiting for RD (id={torrent_id}) ...")

        async def _rd_progress(pct: int):
            await _log(job_id, f"RD progress: {pct}%")
            await update_job(job_id, progress=pct / 100 * 0.3)

        rd_links = await self._rd.wait_until_downloaded(torrent_id, on_progress=_rd_progress)
        await _log(job_id, f"RD ready -- unrestricting {len(rd_links)} link(s) ...")
        unrestricted = await self._rd.unrestrict_all(rd_links)

        if is_season_pack:
            # Filter to video files; fall back to all if filter is too aggressive
            video_files = [
                (u, s) for u, s in unrestricted
                if _is_video_url(u) or (s or 0) > 50 * 1024 * 1024
            ]
            files = video_files or unrestricted
            # Sort by filename so episodes come out in order
            files.sort(key=lambda x: x[0].split("?")[0].split("/")[-1].lower())
            await _log(job_id, f"Season pack: {len(files)} episode file(s)")
            return files
        else:
            unrestricted.sort(key=lambda x: x[1] or 0, reverse=True)
            return [unrestricted[0]]

    # ------------------------------------------------------------------
    # Shared: download + organise
    # ------------------------------------------------------------------

    async def _download_and_organize(
        self,
        job_id: str,
        files: list[tuple[str, Optional[int]]],
        media: MediaInfo,
        best: ScoredStream,
        staging_dir: Path,
    ) -> None:
        total_size = sum(s or 0 for _, s in files) or None
        await update_job(job_id, status=JobStatus.DOWNLOADING, size_bytes=total_size)

        last_final_path: Optional[Path] = None

        for i, (dl_url, fl_size) in enumerate(files):
            file_name = _filename_from_url(dl_url) or f"{job_id}_{i}.mkv"
            staging_path = staging_dir / file_name

            prefix = f"[{i+1}/{len(files)}] " if len(files) > 1 else ""
            await _log(job_id, f"{prefix}Downloading: {file_name}")
            await self._download(job_id, dl_url, staging_path, fl_size)

            # For season packs, detect episode number from filename
            if media.episode is None and media.type in ("tv", "anime"):
                ep_num = _episode_from_filename(file_name)
                ep_media = dc_replace(media, episode=ep_num) if ep_num is not None else media
            else:
                ep_media = media

            await update_job(job_id, status=JobStatus.ORGANIZING)
            final_path = self._organizer.organize(staging_path, ep_media, best)
            await _log(job_id, f"Organised -> {final_path}")
            last_final_path = final_path

        if last_final_path:
            await update_job(
                job_id,
                status=JobStatus.COMPLETE,
                file_path=str(last_final_path),
                progress=1.0,
                downloaded_bytes=total_size or 0,
            )
            await _log(job_id, f"Done ({len(files)} file(s))")
            await _save_poster(media, last_final_path)

    # ------------------------------------------------------------------
    # Downloader
    # ------------------------------------------------------------------

    async def _download(
        self,
        job_id: str,
        url: str,
        dest: Path,
        total_size: Optional[int],
    ) -> None:
        downloaded = 0
        chunk_size = settings.CHUNK_SIZE

        async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                cl = response.headers.get("content-length")
                if cl and cl.isdigit():
                    total_size = int(cl)
                    await update_job(job_id, size_bytes=total_size)

                async with aiofiles.open(dest, "wb") as fh:
                    async for chunk in response.aiter_bytes(chunk_size):
                        await fh.write(chunk)
                        downloaded += len(chunk)

                        if total_size and total_size > 0:
                            pct = 0.3 + (downloaded / total_size) * 0.7
                        else:
                            pct = 0.5

                        await update_job(
                            job_id,
                            downloaded_bytes=downloaded,
                            progress=min(pct, 0.99),
                        )

        await _log(job_id, f"Download complete: {downloaded / 1024**3:.2f} GB")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _filename_from_url(url: str) -> Optional[str]:
    try:
        import urllib.parse
        path = url.split("?")[0].rstrip("/")
        name = urllib.parse.unquote(path.split("/")[-1])
        name = re.sub(r"[?&=].*", "", name)
        if name and "." in name:
            return name
    except Exception:
        pass
    return None


def _is_video_url(url: str) -> bool:
    name = url.split("?")[0].rstrip("/").split("/")[-1].lower()
    return any(name.endswith(ext) for ext in _VIDEO_EXTS)


def _episode_from_filename(name: str) -> Optional[int]:
    """Parse episode number from filenames like Show.S01E03.mkv -> 3."""
    m = re.search(r"[Ss]\d{1,2}[Ee](\d{1,3})", name)
    if m:
        return int(m.group(1))
    return None


async def _save_poster(media: MediaInfo, final_path: Path) -> None:
    """Download the TMDB poster to the central Posters directory.

    Named after the top-level title folder so it stays separate from video files:
      Movies   → Posters/Inception (2010).jpg
      TV/anime → Posters/Breaking Bad.jpg
    """
    if not media.poster_url:
        return

    # Derive the title folder name (one level up for movies, two for TV/anime)
    if media.type == "movie":
        folder_name = final_path.parent.name          # "Inception (2010)"
    else:
        folder_name = final_path.parent.parent.name   # "Breaking Bad"

    posters_dir = Path(settings.POSTERS_DIR)
    posters_dir.mkdir(parents=True, exist_ok=True)
    poster_file = posters_dir / f"{folder_name}.jpg"

    if poster_file.exists():
        return

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(media.poster_url)
            r.raise_for_status()
            async with aiofiles.open(poster_file, "wb") as f:
                await f.write(r.content)
        logger.info("Saved poster -> %s", poster_file)
    except Exception as exc:
        logger.warning("Could not download poster: %s", exc)


async def _log(job_id: str, msg: str) -> None:
    logger.info("[job %s] %s", job_id[:8], msg)
    await append_log(job_id, msg)
