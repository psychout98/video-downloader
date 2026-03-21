"""
Download queue endpoints.

POST /api/search             Search TMDB + torrent sources, return stream options
POST /api/download           Queue a download (auto-pick OR use pre-selected stream)
POST /api/jobs/{id}/retry    Re-queue a failed/cancelled job
GET  /api/jobs               List all jobs (latest 200)
GET  /api/jobs/{id}          Get a single job
DELETE /api/jobs/{id}        Cancel / delete a job
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import state
from ..auth import check_auth
from ..config import settings
from ..database import (
    JobStatus,
    create_job,
    delete_job,
    get_all_jobs,
    get_job,
    update_job,
)

router = APIRouter(prefix="/api", tags=["jobs"])
logger = logging.getLogger(__name__)


# ── Request models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str

class DownloadRequest(BaseModel):
    query:        Optional[str] = None
    search_id:    Optional[str] = None
    stream_index: Optional[int] = None


# ── Search ────────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(body: SearchRequest, request: Request):
    """Search TMDB then collect RD-cached torrent options for the title."""
    check_auth(request)
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    state.prune_searches()

    # 1. TMDB metadata lookup
    try:
        media = await state.tmdb.search(body.query.strip())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"TMDB search failed: {exc}")

    # 2. Collect streams — only RD-cached results are shown in the UI
    streams = []
    stream_warning: Optional[str] = None

    try:
        from ..clients.realdebrid_client import RealDebridClient as _RDC
        _rd_check = _RDC(settings.REAL_DEBRID_API_KEY)

        if media.is_anime:
            nyaa_results = await state.nyaa.search(media)
            for s in nyaa_results:
                if s.info_hash and await _rd_check.is_cached(s.info_hash):
                    s.is_cached_rd = True
                    streams.append(s)

        # Torrentio with RD key already filters to cached-only
        cached = await state.torrentio.get_streams(media, cached_only=True)
        streams.extend(cached)

    except Exception as exc:
        # Check if this is an HTTP error from Torrentio (e.g. 403 = bad RD key)
        http_resp = getattr(exc, "response", None)
        status_code = getattr(http_resp, "status_code", None)
        if status_code == 403:
            stream_warning = (
                "Real-Debrid API key rejected (403 Forbidden). "
                "Please verify your key in Settings and save again."
            )
        elif status_code is not None:
            stream_warning = f"Stream service returned HTTP {status_code}. Try again later."
        else:
            stream_warning = f"Stream fetch failed: {exc}"
        logger.warning("Stream fetch failed for %r: %s", body.query, exc)

    if not streams and stream_warning is None:
        stream_warning = (
            f"No RD-cached torrents found for '{media.display_name}'. "
            "Try a different query or check back later."
        )

    # 3. Score and rank (top 20)
    ranked = state.scorer.rank(streams)
    search_id = str(uuid.uuid4())

    stream_dicts = [
        {
            "index":       idx,
            "name":        s.name,
            "info_hash":   s.info_hash,
            "download_url": s.download_url,
            "size_bytes":  s.size_bytes,
            "seeders":     s.seeders,
            "is_cached_rd": s.is_cached_rd,
            "quality_str": s.quality_str,
            "score":       s.score,
            "resolution":  s.resolution,
            "source":      s.source,
            "hdr":         s.hdr,
            "audio":       s.audio,
            "channels":    s.channels,
            "magnet":      s.magnet,
            "file_idx":    s.file_idx,
        }
        for idx, s in enumerate(ranked[:20])
    ]

    media_dict = {
        "title":          media.title,
        "year":           media.year,
        "imdb_id":        media.imdb_id,
        "tmdb_id":        media.tmdb_id,
        "type":           media.type,
        "season":         media.season,
        "episode":        media.episode,
        "is_anime":       media.is_anime,
        "episode_titles": media.episode_titles,
        "overview":       media.overview,
        "poster_path":    media.poster_path,
        "poster_url":     media.poster_url,
    }

    state.searches[search_id] = {
        "media":   media_dict,
        "streams": stream_dicts,
        "expires": time.time() + state.SEARCH_TTL,
    }

    return {
        "search_id": search_id,
        "media":     media_dict,
        "streams":   stream_dicts,
        "warning":   stream_warning,
    }


# ── Download ──────────────────────────────────────────────────────────────────

@router.post("/download", status_code=201)
async def request_download(body: DownloadRequest, request: Request):
    """Queue a download.  Either pick a stream by search_id + stream_index,
    or pass a free-text query for auto-selection (Siri / headless mode)."""
    check_auth(request)

    # Confirmed stream from UI
    if body.search_id and body.stream_index is not None:
        cached = state.searches.get(body.search_id)
        if not cached:
            raise HTTPException(
                status_code=404, detail="Search session expired — please search again"
            )
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
        logger.info(
            "New job %s: user picked stream #%d for %r",
            job["id"][:8], body.stream_index, title,
        )
        return {"job_id": job["id"], "status": "pending", "message": f"Queued: {title}"}

    # Auto-pick / headless
    if not body.query or not body.query.strip():
        raise HTTPException(
            status_code=422, detail="Provide either 'query' or 'search_id'+'stream_index'"
        )
    job = await create_job(body.query.strip())
    logger.info("New auto job %s: %r", job["id"][:8], body.query)
    return {
        "job_id": job["id"],
        "status": "pending",
        "message": f"Download queued: {body.query!r}",
    }


# ── Job CRUD ──────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs():
    return {"jobs": await get_all_jobs(limit=200)}


@router.get("/jobs/{job_id}")
async def get_job_detail(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}")
async def cancel_or_delete_job(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if state.processor:
        state.processor.cancel_job(job_id)
    if job["status"] in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED):
        await delete_job(job_id)
        return {"message": "Job deleted"}
    await update_job(job_id, status=JobStatus.CANCELLED)
    return {"message": "Job cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request):
    check_auth(request)
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400, detail="Only failed/cancelled jobs can be retried"
        )
    await update_job(
        job_id,
        status=JobStatus.PENDING, error=None, progress=0.0,
        downloaded_bytes=0, log="",
    )
    return {"message": "Job re-queued"}
