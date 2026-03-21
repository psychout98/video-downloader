"""
Media library endpoints.

GET  /api/library                   Scan library, return card list
GET  /api/library/poster            Serve a cached poster image file
GET  /api/library/poster/tmdb       Fetch poster from TMDB, cache, and serve it
POST /api/library/refresh           Unified refresh: normalize + smart poster fetch
GET  /api/library/episodes          List episodes for a TV/anime show
GET  /api/progress                  Get watch progress for a file
POST /api/progress                  Save watch progress for a file
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import httpx

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .. import state
from ..config import settings

router = APIRouter(prefix="/api", tags=["library"])
logger = logging.getLogger(__name__)

_POSTER_NAMES = (
    "poster.jpg", "poster.png", "movie.jpg",
    "folder.jpg", "thumb.jpg", "cover.jpg",
)
_VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"}
_SXEX_RE   = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")
_S_ONLY_RE = re.compile(r"[Ss]eason\s*(\d{1,2})|[Ss](\d{1,2})\b", re.I)


def _safe(s: str) -> str:
    """Strip characters illegal in Windows filenames."""
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


# ── Library scan ──────────────────────────────────────────────────────────────

@router.get("/library")
async def get_library(force: bool = False):
    items = state.library.scan(force=force)
    return {"items": items, "count": len(items)}


# ── Poster: serve cached file ─────────────────────────────────────────────────

@router.get("/library/poster")
async def get_poster(path: str):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Poster not found")
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="Not an image file")
    return FileResponse(str(p))


# ── Poster: fetch from TMDB ─────────────────────────────────────────────────

@router.get("/library/poster/tmdb")
async def get_poster_tmdb(
    title:  str,
    folder: str,
    year:   Optional[int] = None,
    type:   str = "movie",
):
    """Look up a poster on TMDB using fuzzy resolution, cache it, and serve it."""
    folder_path = Path(folder)
    posters_dir = Path(settings.POSTERS_DIR)

    def _check_cached(key: str) -> Optional[Path]:
        safe = _safe(key)
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            p = posters_dir / f"{safe}{ext}"
            if p.exists() and p.is_file():
                return p
        return None

    # 1. Check cache
    input_key   = f"{title} ({year})" if year else title
    folder_name = folder_path.name
    for key in (input_key, folder_name):
        hit = _check_cached(key)
        if hit:
            return FileResponse(str(hit))

    # 2. Legacy: poster inside the media folder
    for name in _POSTER_NAMES:
        p = folder_path / name
        if p.exists() and p.is_file():
            return FileResponse(str(p))

    # 3. Resolve via TMDB
    if not state.tmdb:
        raise HTTPException(status_code=503, detail="TMDB client not initialised")

    try:
        canonical_title, canonical_year, poster_path = await state.tmdb.fuzzy_resolve(
            title, media_type=type, year=year
        )
    except Exception as exc:
        logger.warning("TMDB fuzzy_resolve failed for '%s': %s", title, exc)
        raise HTTPException(status_code=404, detail=str(exc))

    if not poster_path:
        raise HTTPException(status_code=404, detail="No poster available on TMDB")

    # 4. Download the image
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://image.tmdb.org/t/p/w500{poster_path}")
            r.raise_for_status()
            poster_data = r.content
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Poster download failed: {exc}")

    # 5. Cache under the canonical key
    canonical_key = f"{canonical_title} ({canonical_year})" if canonical_year else canonical_title
    try:
        posters_dir.mkdir(parents=True, exist_ok=True)
        cache_file = posters_dir / f"{_safe(canonical_key)}.jpg"
        cache_file.write_bytes(poster_data)
        logger.info("Cached TMDB poster '%s' → %s", canonical_key, cache_file.name)
    except Exception as exc:
        logger.warning("Could not cache poster for '%s': %s", canonical_key, exc)

    return Response(content=poster_data, media_type="image/jpeg")


# ── Unified refresh ──────────────────────────────────────────────────────────

@router.post("/library/refresh")
async def refresh_library():
    """Unified refresh: normalize folder names + smart poster fetch.

    Scans every library directory, resolves canonical titles via TMDB,
    renames folders that don't match, and fetches missing/changed posters.
    """
    if not state.tmdb or not state.library:
        raise HTTPException(status_code=503, detail="Services not initialised")

    summary = await state.library.refresh(state.tmdb)
    return summary


# ── Episodes ──────────────────────────────────────────────────────────────────

@router.get("/library/episodes")
async def get_episodes(folder: str, folder_archive: Optional[str] = None):
    """Return all episodes inside a TV/anime show folder, grouped by season."""
    show_dir = Path(folder)
    if not show_dir.exists() or not show_dir.is_dir():
        raise HTTPException(status_code=404, detail="Show folder not found")

    dirs_to_scan: list[Path] = [show_dir]
    if folder_archive:
        arch = Path(folder_archive)
        if arch.exists() and arch.is_dir() and arch.resolve() != show_dir.resolve():
            dirs_to_scan.append(arch)

    seasons: dict[int, list[dict]] = {}
    seen_filenames: set[str] = set()

    for scan_dir in dirs_to_scan:
        for video in sorted(scan_dir.rglob("*")):
            if not video.is_file() or video.suffix.lower() not in _VIDEO_EXTS:
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
                ms      = _S_ONLY_RE.search(video.parent.name)
                season  = int(ms.group(1) or ms.group(2)) if ms else 1
                episode = 0
                ep_title = stem

            progress = (
                state.progress_store.get(str(video)) if state.progress_store else None
            )
            pct = 0
            if progress and progress.get("duration_ms"):
                pct = round(
                    min(progress["position_ms"] / progress["duration_ms"], 1.0) * 100
                )

            seasons.setdefault(season, []).append({
                "season":       season,
                "episode":      episode,
                "title":        ep_title,
                "filename":     video.name,
                "path":         str(video),
                "size_bytes":   video.stat().st_size,
                "progress_pct": pct,
                "position_ms":  progress.get("position_ms", 0) if progress else 0,
                "duration_ms":  progress.get("duration_ms", 0) if progress else 0,
            })

    for eps in seasons.values():
        eps.sort(key=lambda e: (e["episode"], e["filename"]))

    return {
        "seasons": [
            {"season": s, "episodes": eps}
            for s, eps in sorted(seasons.items())
        ]
    }


# ── Watch progress ────────────────────────────────────────────────────────────

class ProgressUpdateRequest(BaseModel):
    path:        str
    position_ms: int
    duration_ms: int


@router.get("/progress")
async def get_progress(path: str):
    d = state.progress_store.get(path) if state.progress_store else None
    return d or {}


@router.post("/progress")
async def save_progress(body: ProgressUpdateRequest):
    if state.progress_store:
        state.progress_store.save(body.path, body.position_ms, body.duration_ms)
    return {"ok": True}
