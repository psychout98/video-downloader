"""
Media library endpoints.

GET  /api/library                   Scan library, return card list
GET  /api/library/poster            Serve a cached poster image file
POST /api/library/posters/clear     Delete all cached posters and force rescan
GET  /api/library/poster/tmdb       Fetch poster from TMDB, cache, and serve it
GET  /api/library/episodes          List episodes for a TV/anime show
GET  /api/progress                  Get watch progress for a file
POST /api/progress                  Save watch progress for a file
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

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
    """Strip characters illegal in Windows filenames (e.g. colon in 'Thor: …')."""
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


# ── Poster: clear cache ───────────────────────────────────────────────────────

@router.post("/library/posters/clear")
async def clear_poster_cache():
    """Delete all cached poster images so they are re-fetched from TMDB on
    the next library load.  Also forces a library rescan so stale poster
    paths are cleared from the in-memory cache."""
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

    if state.library:
        state.library.scan(force=True)

    logger.info("Poster cache cleared: %d files deleted", deleted)
    return {"ok": True, "deleted": deleted, "errors": errors}


# ── Poster: fetch from TMDB ───────────────────────────────────────────────────

@router.get("/library/poster/tmdb")
async def get_poster_tmdb(
    title:  str,
    folder: str,
    year:   Optional[int] = None,
    type:   str = "movie",
):
    """Look up a poster on TMDB, cache it to POSTERS_DIR, and serve it.

    Uses ``/search/movie`` for movies and ``/search/tv`` for TV/anime so the
    correct result type is always returned.  Filters by year when available.
    If a matching poster is already cached it is served immediately.
    """
    import httpx as _httpx

    folder_path = Path(folder)
    posters_dir = Path(settings.POSTERS_DIR)

    # Canonical poster key: "Title (Year)" or just "Title"
    poster_key  = f"{title} ({year})" if year else title
    folder_name = folder_path.name

    def _check_cached(key: str) -> Optional[Path]:
        safe = _safe(key)
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            p = posters_dir / f"{safe}{ext}"
            if p.exists() and p.is_file():
                return p
        return None

    # 1. Check central poster cache — title key first, then folder-name key
    hit = _check_cached(poster_key)
    if hit:
        return FileResponse(str(hit))
    if folder_name != poster_key:
        hit = _check_cached(folder_name)
        if hit:
            return FileResponse(str(hit))

    # 2. Legacy fallback: poster stored inside the media folder itself
    for name in _POSTER_NAMES:
        p = folder_path / name
        if p.exists() and p.is_file():
            return FileResponse(str(p))

    # 3. Fetch from TMDB
    tmdb_base     = "https://api.themoviedb.org/3"
    default_params = {"api_key": settings.TMDB_API_KEY}

    try:
        async with _httpx.AsyncClient(
            base_url=tmdb_base, params=default_params, timeout=15
        ) as client:
            is_tv    = type in ("tv", "anime")
            endpoint = "/search/tv" if is_tv else "/search/movie"
            params: dict = {"query": title, "include_adult": False}
            if year:
                params["first_air_date_year" if is_tv else "year"] = year

            r = await client.get(endpoint, params=params)
            r.raise_for_status()
            results = r.json().get("results", [])

            # Retry without year if the year-filtered search returns nothing
            if not results and year:
                params.pop("first_air_date_year", None)
                params.pop("year", None)
                r = await client.get(endpoint, params=params)
                r.raise_for_status()
                results = r.json().get("results", [])

            if not results:
                raise HTTPException(
                    status_code=404, detail=f"No TMDB results for '{title}'"
                )

            # Pick the best match: prefer exact title + year, else most popular
            def _score(item: dict) -> tuple:
                tmdb_title = (item.get("title") or item.get("name") or "").lower()
                exact      = tmdb_title == title.lower()
                date_str   = item.get("release_date") or item.get("first_air_date") or ""
                item_year  = int(date_str[:4]) if date_str[:4].isdigit() else 0
                year_match = item_year == year if year else True
                return (exact and year_match, exact, item.get("popularity", 0))

            results.sort(key=_score, reverse=True)
            best        = results[0]
            poster_path = best.get("poster_path")
            if not poster_path:
                raise HTTPException(
                    status_code=404, detail="No poster available on TMDB"
                )

            poster_url  = f"https://image.tmdb.org/t/p/w500{poster_path}"
            pr          = await client.get(poster_url)
            pr.raise_for_status()
            poster_data = pr.content

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=404, detail=f"TMDB poster fetch failed: {exc}"
        )

    # Cache the poster to disk using a sanitized filename
    try:
        posters_dir.mkdir(parents=True, exist_ok=True)
        poster_file = posters_dir / f"{_safe(poster_key)}.jpg"
        poster_file.write_bytes(poster_data)
        logger.info("Cached TMDB poster for '%s' → %s", title, poster_file.name)
    except Exception as exc:
        logger.warning("Could not cache poster for '%s': %s", title, exc)

    return Response(content=poster_data, media_type="image/jpeg")


# ── Episodes ──────────────────────────────────────────────────────────────────

@router.get("/library/episodes")
async def get_episodes(folder: str, folder_archive: Optional[str] = None):
    """Return all episodes inside a TV/anime show folder, grouped by season.

    Optionally also scans *folder_archive* so episodes that have been
    watched and moved to the archive drive still appear in the list.
    """
    show_dir = Path(folder)
    if not show_dir.exists() or not show_dir.is_dir():
        raise HTTPException(status_code=404, detail="Show folder not found")

    # Build the list of directories to scan; deduplicate resolved paths
    dirs_to_scan: list[Path] = [show_dir]
    if folder_archive:
        arch = Path(folder_archive)
        if arch.exists() and arch.is_dir() and arch.resolve() != show_dir.resolve():
            dirs_to_scan.append(arch)

    seasons: dict[int, list[dict]] = {}
    seen_filenames: set[str] = set()   # deduplicate across both drives

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
