"""
Download queue endpoints.

POST /api/search             Search TMDB + Torrentio, return stream options
POST /api/download           Queue a download using a pre-selected stream
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

# Maximum number of cached search results to keep in memory
_MAX_SEARCH_CACHE = 50


# ── Request models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str

class DownloadRequest(BaseModel):
    search_id:    str
    stream_index: int


# ── Search ────────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(body: SearchRequest):
    """Search TMDB then collect torrent options for the title.

    Returns both cached and uncached streams, sorted by cached first
    then by file size descending. No quality scoring is applied.
    """
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    # Prune expired searches and enforce size cap
    state.prune_searches()
    if len(state.searches) >= _MAX_SEARCH_CACHE:
        # Remove oldest entries
        oldest = sorted(state.searches.items(), key=lambda kv: kv[1]["expires"])
        for k, _ in oldest[:len(state.searches) - _MAX_SEARCH_CACHE + 1]:
            del state.searches[k]

    # 1. TMDB metadata lookup
    try:
        media = await state.tmdb.search(body.query.strip())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"TMDB search failed: {exc}")

    # 2. Collect streams from Torrentio (cached first, then all)
    streams = []
    stream_warning: Optional[str] = None

    try:
        cached = await state.torrentio.get_streams(media, cached_only=True)
        streams.extend(cached)

        # If no cached results, also fetch uncached
        if not cached:
            all_streams = await state.torrentio.get_streams(media, cached_only=False)
            streams.extend(all_streams)

    except Exception as exc:
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
            f"No torrents found for '{media.display_name}'. "
            "Try a different query or check back later."
        )

    # 3. Build response (already sorted by Torrentio client: cached first, then by size)
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
            "magnet":      s.magnet,
            "file_idx":    s.file_idx,
        }
        for idx, s in enumerate(streams[:20])
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
async def request_download(body: DownloadRequest):
    """Queue a download using a pre-selected stream from a search result."""
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
        torrent_name=stream_d["name"][:120],
    )
    logger.info(
        "New job %s: user picked stream #%d for %r",
        job["id"][:8], body.stream_index, title,
    )
    return {"job_id": job["id"], "status": "pending", "message": f"Queued: {title}"}


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
async def retry_job(job_id: str):
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
