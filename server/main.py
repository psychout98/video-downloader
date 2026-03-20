"""
FastAPI application entry point.

Routes
------
POST /api/search                  Search TMDB + torrent sources, return stream options
POST /api/download                Queue a download (auto-pick best OR use pre-selected stream)
POST /api/jobs/{id}/retry         Re-queue a failed/cancelled job
GET  /api/jobs                    List all jobs
GET  /api/jobs/{job_id}           Get a single job
DELETE /api/jobs/{job_id}         Cancel / delete a job
GET  /api/status                  Server health + config summary

GET  /api/library                 Scan media library, return card list
GET  /api/library/poster          Serve a poster image file
POST /api/library/posters/clear   Delete all cached posters and force rescan

GET  /api/mpc/status              MPC-BE player state
POST /api/mpc/command             Send a command to MPC-BE
POST /api/mpc/open                Tell MPC-BE to open a specific file

GET  /                            Web UI
"""
from __future__ import annotations

import asyncio as _asyncio
import dataclasses
import json
import logging
import os
import re
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .database import (
    JobStatus,
    create_job,
    delete_job,
    get_all_jobs,
    get_job,
    init_db,
    update_job,
)
from .job_processor import JobProcessor
from .library_scanner import LibraryScanner
from .mpc_client import MPCClient
from .nyaa_client import NyaaClient
from .quality_scorer import QualityScorer
from .tmdb_client import TMDBClient
from .torrentio_client import TorrentioClient
from .progress_store import ProgressStore
from .watch_tracker import WatchTracker

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Paths used by settings/stop helpers
_ROOT_DIR  = Path(__file__).parent.parent
_ENV_FILE  = _ROOT_DIR / ".env"
_PID_FILE  = _ROOT_DIR / "server.pid"
_LOG_FILE  = _ROOT_DIR / "logs" / "server.log"
_file_log_handler: Optional[logging.FileHandler] = None

# ---------------------------------------------------------------------------
# In-memory search cache  {search_id: {media, streams, expires}}
# ---------------------------------------------------------------------------
_searches: dict[str, dict] = {}
SEARCH_TTL = 300  # seconds


def _prune_searches():
    now = time.time()
    stale = [k for k, v in _searches.items() if v["expires"] < now]
    for k in stale:
        del _searches[k]


# ---------------------------------------------------------------------------
# App-level singletons (created in lifespan)
# ---------------------------------------------------------------------------
_processor: Optional[JobProcessor] = None
_tmdb: Optional[TMDBClient] = None
_torrentio: Optional[TorrentioClient] = None
_nyaa: Optional[NyaaClient] = None
_scorer: Optional[QualityScorer] = None
_library: Optional[LibraryScanner] = None
_mpc: Optional[MPCClient] = None
_watch_tracker: Optional[WatchTracker] = None
_progress_store: Optional[ProgressStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _processor, _tmdb, _torrentio, _nyaa, _scorer, _library, _mpc, _watch_tracker, _progress_store
    global _file_log_handler

    # ── File logging ──────────────────────────────────────────────────────
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _file_log_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        _file_log_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logging.getLogger().addHandler(_file_log_handler)
    except Exception as exc:
        logger.warning("Could not set up file logging: %s", exc)

    # ── PID file ─────────────────────────────────────────────────────────
    try:
        _PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    except Exception as exc:
        logger.warning("Could not write PID file: %s", exc)

    logger.info("Media Downloader starting …")
    await init_db()

    _tmdb           = TMDBClient(settings.TMDB_API_KEY)
    _torrentio      = TorrentioClient(settings.REAL_DEBRID_API_KEY)
    _nyaa           = NyaaClient()
    _scorer         = QualityScorer()
    _library        = LibraryScanner(
        settings.MOVIES_DIR,         settings.TV_DIR,         settings.ANIME_DIR,
        settings.MOVIES_DIR_ARCHIVE, settings.TV_DIR_ARCHIVE, settings.ANIME_DIR_ARCHIVE,
    )
    _mpc            = MPCClient(settings.MPC_BE_URL)
    _progress_store = ProgressStore(settings.PROGRESS_FILE)

    _processor = JobProcessor()
    _processor.start()

    _watch_tracker = WatchTracker(_mpc, _progress_store)
    _watch_tracker.start()

    yield

    if _watch_tracker:
        _watch_tracker.stop()
    if _processor:
        _processor.stop()
    if _tmdb:
        await _tmdb.close()
    logger.info("Media Downloader stopped")

    # ── Clean up PID file ─────────────────────────────────────────────────
    try:
        _PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    # ── Remove file log handler ────────────────────────────────────────────
    if _file_log_handler:
        logging.getLogger().removeHandler(_file_log_handler)
        _file_log_handler.close()


app = FastAPI(title="Media Downloader", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _check_auth(request: Request) -> None:
    if settings.SECRET_KEY == "change-me":
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if auth.removeprefix("Bearer ").strip() != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str

class DownloadRequest(BaseModel):
    query: Optional[str] = None
    search_id: Optional[str] = None
    stream_index: Optional[int] = None

class MPCCommandRequest(BaseModel):
    command: int
    position_ms: Optional[int] = None   # for seek

class MPCOpenRequest(BaseModel):
    path: str
    playlist: Optional[list[str]] = None   # if provided, open all files as a playlist


# ---------------------------------------------------------------------------
# Search — returns stream options without starting a download
# ---------------------------------------------------------------------------

@app.post("/api/search")
async def search(body: SearchRequest, request: Request):
    _check_auth(request)
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    _prune_searches()

    # 1. TMDB
    try:
        media = await _tmdb.search(body.query.strip())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"TMDB search failed: {exc}")

    # 2. Collect streams — UI shows RD-cached results only
    from .realdebrid_client import RealDebridClient as _RDC
    _rd_check = _RDC(settings.REAL_DEBRID_API_KEY)
    streams = []

    if media.is_anime:
        nyaa_results = await _nyaa.search(media)
        for s in nyaa_results:
            if s.info_hash and await _rd_check.is_cached(s.info_hash):
                s.is_cached_rd = True
                streams.append(s)

    # Torrentio with RD key already filters to cached-only
    cached = await _torrentio.get_streams(media, cached_only=True)
    streams.extend(cached)

    if not streams:
        raise HTTPException(
            status_code=404,
            detail=f"No RD-cached torrents found for '{media.display_name}'. "
                   "Try a different query or check back later."
        )

    # 3. Score and rank
    ranked = _scorer.rank(streams)

    # 4. Serialise to plain dicts (top 20)
    search_id = str(uuid.uuid4())
    stream_dicts = []
    for idx, s in enumerate(ranked[:20]):
        d = {
            "index": idx,
            "name": s.name,
            "info_hash": s.info_hash,
            "download_url": s.download_url,
            "size_bytes": s.size_bytes,
            "seeders": s.seeders,
            "is_cached_rd": s.is_cached_rd,
            "quality_str": s.quality_str,
            "score": s.score,
            "resolution": s.resolution,
            "source": s.source,
            "hdr": s.hdr,
            "audio": s.audio,
            "channels": s.channels,
            "magnet": getattr(s, "_magnet", None),
            "file_idx": getattr(s, "_file_idx", None),
        }
        stream_dicts.append(d)

    media_dict = {
        "title": media.title,
        "year": media.year,
        "imdb_id": media.imdb_id,
        "tmdb_id": media.tmdb_id,
        "type": media.type,
        "season": media.season,
        "episode": media.episode,
        "is_anime": media.is_anime,
        "episode_titles": media.episode_titles,
        "overview": media.overview,
        "poster_path": media.poster_path,
        "poster_url": media.poster_url,
    }

    _searches[search_id] = {
        "media": media_dict,
        "streams": stream_dicts,
        "expires": time.time() + SEARCH_TTL,
    }

    return {
        "search_id": search_id,
        "media": media_dict,
        "streams": stream_dicts,
    }


# ---------------------------------------------------------------------------
# Download — auto-pick OR confirmed stream choice
# ---------------------------------------------------------------------------

@app.post("/api/download", status_code=201)
async def request_download(body: DownloadRequest, request: Request):
    _check_auth(request)

    # ── Confirmed stream from UI ────────────────────────────────────────
    if body.search_id and body.stream_index is not None:
        cached = _searches.get(body.search_id)
        if not cached:
            raise HTTPException(status_code=404, detail="Search session expired — please search again")
        if body.stream_index >= len(cached["streams"]):
            raise HTTPException(status_code=422, detail="stream_index out of range")

        stream_d = cached["streams"][body.stream_index]
        media_d  = cached["media"]
        title    = media_d.get("title", "Unknown")

        stream_data_json = json.dumps({"media": media_d, "stream": stream_d})
        job = await create_job(
            query=f"{title} (user-selected stream #{body.stream_index})",
            stream_data=stream_data_json,
        )
        # Pre-fill known fields immediately
        await update_job(
            job["id"],
            title=media_d["title"],
            year=media_d.get("year"),
            imdb_id=media_d.get("imdb_id"),
            type=media_d.get("type"),
            season=media_d.get("season"),
            episode=media_d.get("episode"),
            quality=stream_d.get("quality_str"),
            torrent_name=stream_d["name"][:120],
        )
        logger.info("New job %s: user picked stream #%d for %r", job["id"][:8], body.stream_index, title)
        return {"job_id": job["id"], "status": "pending", "message": f"Queued: {title}"}

    # ── Auto-pick (Siri / headless) ─────────────────────────────────────
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=422, detail="Provide either 'query' or 'search_id'+'stream_index'")

    job = await create_job(body.query.strip())
    logger.info("New auto job %s: %r", job["id"][:8], body.query)
    return {"job_id": job["id"], "status": "pending", "message": f"Download queued: {body.query!r}"}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
async def list_jobs():
    return {"jobs": await get_all_jobs(limit=200)}


@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/api/jobs/{job_id}")
async def cancel_or_delete_job(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if _processor:
        _processor.cancel_job(job_id)
    if job["status"] in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED):
        await delete_job(job_id)
        return {"message": "Job deleted"}
    await update_job(job_id, status=JobStatus.CANCELLED)
    return {"message": "Job cancelled"}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request):
    _check_auth(request)
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Only failed/cancelled jobs can be retried")
    await update_job(job_id, status=JobStatus.PENDING, error=None, progress=0.0,
                     downloaded_bytes=0, log="")
    return {"message": "Job re-queued"}


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.get("/api/library")
async def get_library(force: bool = False):
    items = _library.scan(force=force)
    return {"items": items, "count": len(items)}


@app.get("/api/library/poster")
async def get_poster(path: str):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Poster not found")
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="Not an image file")
    return FileResponse(str(p))


_POSTER_NAMES = ("poster.jpg", "poster.png", "movie.jpg", "folder.jpg", "thumb.jpg", "cover.jpg")


@app.post("/api/library/posters/clear")
async def clear_poster_cache():
    """Delete all cached poster images so they are re-fetched from TMDB on
    next library load.  Also forces an immediate library rescan so the UI
    gets fresh data (without stale poster paths) right away."""
    import shutil as _shutil

    posters_dir = Path(settings.POSTERS_DIR)
    deleted = 0
    errors: list[str] = []
    if posters_dir.exists():
        for f in posters_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".jpg", ".png", ".jpeg", ".webp"):
                try:
                    f.unlink()
                    deleted += 1
                except Exception as exc:
                    errors.append(str(exc))

    # Force library rescan so poster fields return None and the UI re-requests
    # them from TMDB.
    if _library:
        _library.scan(force=True)

    logger.info("Poster cache cleared: %d files deleted", deleted)
    return {"ok": True, "deleted": deleted, "errors": errors}


@app.get("/api/library/poster/tmdb")
async def get_poster_tmdb(
    title: str,
    folder: str,
    year: Optional[int] = None,
    type: str = "movie",
):
    """Look up a poster on TMDB using a targeted search, save it to the media
    folder, and return the image.

    Uses /search/movie for movies and /search/tv for TV/anime so the correct
    result type is always returned.  Filters by year when available to avoid
    picking the wrong entry (e.g. remakes).

    If a local poster was already saved it is served directly without hitting
    TMDB again.
    """
    import httpx as _httpx
    from fastapi.responses import Response as _Response

    folder_path = Path(folder)
    posters_dir = Path(settings.POSTERS_DIR)

    # Canonical poster key: "Title (Year)" or "Title" — matches the organizer's
    # folder naming and works even for flat files where folder_path.name would
    # just be "Movies" (the same for every movie in the library).
    poster_key = f"{title} ({year})" if year else title

    # Also derive the folder-based name as a secondary check (works for shows
    # that are always in a per-title subfolder).
    folder_name = folder_path.name

    def _safe(s: str) -> str:
        """Strip characters illegal in Windows filenames (e.g. colon in 'Thor: ...')."""
        return re.sub(r'[\\/:*?"<>|]', "_", s).strip()

    def _check_posters_dir(key: str):
        safe = _safe(key)
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            p = posters_dir / f"{safe}{ext}"
            if p.exists() and p.is_file():
                return p
        return None

    # 1. Check central posters directory — title-based key first
    hit = _check_posters_dir(poster_key)
    if hit:
        return FileResponse(str(hit))

    # 1b. Also check folder-name key (handles shows already saved this way)
    if folder_name != poster_key:
        hit = _check_posters_dir(folder_name)
        if hit:
            return FileResponse(str(hit))

    # 2. Legacy fallback: poster still inside the media folder
    for name in _POSTER_NAMES:
        p = folder_path / name
        if p.exists() and p.is_file():
            return FileResponse(str(p))

    # --- Targeted TMDB search -------------------------------------------
    tmdb_base = "https://api.themoviedb.org/3"
    default_params: dict = {"api_key": settings.TMDB_API_KEY}

    try:
        async with _httpx.AsyncClient(base_url=tmdb_base, params=default_params, timeout=15) as client:
            is_tv = type in ("tv", "anime")
            endpoint = "/search/tv" if is_tv else "/search/movie"
            params: dict = {"query": title, "include_adult": False}
            if year:
                params["first_air_date_year" if is_tv else "year"] = year

            r = await client.get(endpoint, params=params)
            r.raise_for_status()
            results = r.json().get("results", [])

            # If year-filtered search returns nothing, retry without year
            # (handles cases where TMDB year is off by one)
            if not results and year:
                params.pop("first_air_date_year", None)
                params.pop("year", None)
                r = await client.get(endpoint, params=params)
                r.raise_for_status()
                results = r.json().get("results", [])

            if not results:
                raise HTTPException(status_code=404, detail=f"No TMDB results for '{title}'")

            # Pick best match: prefer exact title match at same year, else most popular
            def _score(item: dict) -> tuple:
                tmdb_title = (item.get("title") or item.get("name") or "").lower()
                exact = tmdb_title == title.lower()
                date_str = item.get("release_date") or item.get("first_air_date") or ""
                item_year = int(date_str[:4]) if date_str[:4].isdigit() else 0
                year_match = item_year == year if year else True
                return (exact and year_match, exact, item.get("popularity", 0))

            results.sort(key=_score, reverse=True)
            best = results[0]

            poster_path = best.get("poster_path")
            if not poster_path:
                raise HTTPException(status_code=404, detail="No poster available on TMDB")

            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"

            # Download poster
            pr = await client.get(poster_url)
            pr.raise_for_status()
            poster_data = pr.content

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"TMDB poster fetch failed: {exc}")

    # Persist using the sanitized title-based key.  Sanitization is required on
    # Windows where ':' and other characters are illegal in filenames
    # (e.g. "Thor: Love and Thunder (2022)" would otherwise fail to save).
    try:
        posters_dir.mkdir(parents=True, exist_ok=True)
        poster_file = posters_dir / f"{_safe(poster_key)}.jpg"
        with open(poster_file, "wb") as fh:
            fh.write(poster_data)
        logger.info("Saved TMDB poster for '%s' → %s", title, poster_file)
    except Exception as exc:
        logger.warning("Could not save poster for '%s': %s", title, exc)

    return _Response(content=poster_data, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Episodes + watch progress
# ---------------------------------------------------------------------------

_VIDEO_EXTS_EP = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"}
_SXEX_RE = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")
_S_ONLY_RE = re.compile(r"[Ss]eason\s*(\d{1,2})|[Ss](\d{1,2})\b", re.I)


@app.get("/api/library/episodes")
async def get_episodes(folder: str, folder_archive: Optional[str] = None):
    """Return all episodes inside a TV/anime show folder, grouped by season.

    Optionally also scans *folder_archive* (the SATA copy) so that episodes
    which have already been watched+archived still appear in the list.
    """
    show_dir = Path(folder)
    if not show_dir.exists() or not show_dir.is_dir():
        raise HTTPException(status_code=404, detail="Show folder not found")

    # Collect dirs to scan; use a set of resolved paths to avoid duplicates
    dirs_to_scan: list[Path] = [show_dir]
    if folder_archive:
        arch = Path(folder_archive)
        if arch.exists() and arch.is_dir() and arch.resolve() != show_dir.resolve():
            dirs_to_scan.append(arch)

    seasons: dict[int, list[dict]] = {}
    seen_filenames: set[str] = set()   # deduplicate by filename across both drives

    for scan_dir in dirs_to_scan:
        for video in sorted(scan_dir.rglob("*")):
            if not video.is_file() or video.suffix.lower() not in _VIDEO_EXTS_EP:
                continue
            if video.name in seen_filenames:
                continue
            seen_filenames.add(video.name)

            stem = video.stem
            m = _SXEX_RE.search(stem)
            if m:
                season  = int(m.group(1))
                episode = int(m.group(2))
                ep_title = stem[m.end():].strip(" -–")
            else:
                ms = _S_ONLY_RE.search(video.parent.name)
                season  = int(ms.group(1) or ms.group(2)) if ms else 1
                episode = 0
                ep_title = stem

            progress = _progress_store.get(str(video)) if _progress_store else None
            pct = 0
            if progress and progress.get("duration_ms"):
                pct = round(min(progress["position_ms"] / progress["duration_ms"], 1.0) * 100)

            seasons.setdefault(season, []).append({
                "season":        season,
                "episode":       episode,
                "title":         ep_title,
                "filename":      video.name,
                "path":          str(video),
                "size_bytes":    video.stat().st_size,
                "progress_pct":  pct,
                "position_ms":   progress.get("position_ms", 0) if progress else 0,
                "duration_ms":   progress.get("duration_ms", 0) if progress else 0,
            })

    for eps in seasons.values():
        eps.sort(key=lambda e: (e["episode"], e["filename"]))

    return {
        "seasons": [
            {"season": s, "episodes": eps}
            for s, eps in sorted(seasons.items())
        ]
    }


class ProgressUpdateRequest(BaseModel):
    path:        str
    position_ms: int
    duration_ms: int


@app.get("/api/progress")
async def get_progress(path: str):
    d = _progress_store.get(path) if _progress_store else None
    return d or {}


@app.post("/api/progress")
async def save_progress(body: ProgressUpdateRequest):
    if _progress_store:
        _progress_store.save(body.path, body.position_ms, body.duration_ms)
    return {"ok": True}


# ---------------------------------------------------------------------------
# MPC-BE proxy
# ---------------------------------------------------------------------------

@app.get("/api/mpc/status")
async def mpc_status():
    status_obj = await _mpc.get_status()
    return status_obj.to_dict()


@app.post("/api/mpc/command")
async def mpc_command(body: MPCCommandRequest):
    extra = {}
    if body.position_ms is not None:
        extra["position"] = body.position_ms
    ok = await _mpc.command(body.command, **extra)
    return {"ok": ok}


@app.post("/api/mpc/open")
async def mpc_open(body: MPCOpenRequest):
    import subprocess

    # Build a .m3u playlist when multiple files are provided so MPC-BE
    # autoplays the next episode when the current one finishes.
    files = body.playlist if (body.playlist and len(body.playlist) > 1) else [body.path]

    if len(files) > 1:
        playlist_file = _ROOT_DIR / "data" / "current_playlist.m3u"
        playlist_file.parent.mkdir(parents=True, exist_ok=True)
        with open(playlist_file, "w", encoding="utf-8-sig") as fh:
            fh.write("#EXTM3U\n")
            for p in files:
                fh.write(p + "\n")
        open_path = str(playlist_file)
    else:
        open_path = files[0]

    exe = settings.MPC_BE_EXE
    if not Path(exe).exists():
        raise HTTPException(
            status_code=500,
            detail=f"MPC-BE executable not found at '{exe}'. Set MPC_BE_EXE in your .env file.",
        )

    # Check whether MPC-BE is already running so the UI knows whether to wait
    # for launch.  We always use subprocess.Popen regardless — when MPC-BE is
    # configured in single-instance mode (the default), launching it a second
    # time with a path causes the existing instance to open that file.  This is
    # far more reliable than the /command.html web API which returns HTTP 200
    # even when the command is silently ignored.
    was_running = await _mpc.ping()

    try:
        subprocess.Popen(
            [exe, open_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch MPC-BE: {exc}")

    return {"ok": True, "launched": not was_running}


# ---------------------------------------------------------------------------
# Server status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def server_status():
    return {
        "status": "ok",
        "movies_dir": settings.MOVIES_DIR,
        "tv_dir": settings.TV_DIR,
        "anime_dir": settings.ANIME_DIR,
        "movies_dir_archive": settings.MOVIES_DIR_ARCHIVE,
        "tv_dir_archive": settings.TV_DIR_ARCHIVE,
        "anime_dir_archive": settings.ANIME_DIR_ARCHIVE,
        "watch_threshold_pct": int(settings.WATCH_THRESHOLD * 100),
        "mpc_be_url": settings.MPC_BE_URL,
        "auth_enabled": settings.SECRET_KEY != "change-me",
    }


# ---------------------------------------------------------------------------
# Settings — read / write .env
# ---------------------------------------------------------------------------

# Keys exposed through the settings API (excludes nothing — local service)
_SETTINGS_KEYS = [
    "TMDB_API_KEY", "REAL_DEBRID_API_KEY", "SECRET_KEY",
    "MOVIES_DIR", "TV_DIR", "ANIME_DIR",
    "MOVIES_DIR_ARCHIVE", "TV_DIR_ARCHIVE", "ANIME_DIR_ARCHIVE",
    "DOWNLOADS_DIR", "POSTERS_DIR", "PROGRESS_FILE",
    "MPC_BE_URL", "MPC_BE_EXE",
    "WATCH_THRESHOLD", "HOST", "PORT", "MAX_CONCURRENT_DOWNLOADS",
]


@app.get("/api/settings")
async def get_settings():
    """Return current setting values (from live settings object)."""
    result = {}
    for key in _SETTINGS_KEYS:
        val = getattr(settings, key, None)
        result[key] = val if val is not None else ""
    return result


class SettingsUpdateRequest(BaseModel):
    updates: dict  # {KEY: new_value_str}


@app.post("/api/settings")
async def update_settings(body: SettingsUpdateRequest):
    """Persist updated values to .env using python-dotenv.
    The server must be restarted for changes to take effect."""
    from dotenv import set_key as _dotenv_set_key

    if not _ENV_FILE.exists():
        # Create an empty .env if it doesn't exist yet
        _ENV_FILE.touch()

    written = []
    errors = []
    for key, value in body.updates.items():
        if key not in _SETTINGS_KEYS:
            errors.append(f"Unknown key: {key}")
            continue
        try:
            _dotenv_set_key(str(_ENV_FILE), key, str(value))
            written.append(key)
        except Exception as exc:
            errors.append(f"{key}: {exc}")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return {"ok": True, "written": written, "note": "Restart the server for changes to take effect."}


# ---------------------------------------------------------------------------
# Logs — tail the server log file
# ---------------------------------------------------------------------------

@app.get("/api/logs")
async def get_logs(lines: int = 200):
    """Return the last *lines* lines from the server log file."""
    if not _LOG_FILE.exists():
        return {"lines": [], "note": "No log file found — server may not have been started via the normal launcher."}
    try:
        with open(_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = [l.rstrip() for l in all_lines[-lines:]]
        return {"lines": tail, "total": len(all_lines)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read log: {exc}")


# ---------------------------------------------------------------------------
# Shutdown — graceful stop via the API
# ---------------------------------------------------------------------------

@app.post("/api/shutdown")
async def api_shutdown():
    """Gracefully stop the server process."""
    logger.info("Shutdown requested via API")

    async def _do_shutdown():
        await _asyncio.sleep(0.3)  # let the response be sent first
        os.kill(os.getpid(), signal.SIGTERM)

    _asyncio.create_task(_do_shutdown())
    return {"ok": True, "message": "Server shutting down…"}


# ---------------------------------------------------------------------------
# Static / UI
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def ui():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    logger.error("Unhandled: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
