"""
Media library endpoints.

GET  /api/library                   Scan library, return card list
GET  /api/library/poster            Serve a cached poster image file
POST /api/library/posters/clear     Delete all cached posters and force rescan
GET  /api/library/poster/tmdb       Fetch poster from TMDB, cache, and serve it
POST /api/library/normalize         Rename folders to canonical 'Title (Year)' form
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
from ..core.library_scanner import _extract_title_year

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
    """Look up a poster on TMDB using fuzzy resolution, cache it, and serve it.

    Resolution is delegated to ``TMDBClient.fuzzy_resolve()`` which tries
    type-specific search (with year → without) then TMDB multi-search then
    progressive title truncation, so messy filenames still find a result.
    The poster is cached under the *canonical* TMDB title so subsequent loads
    are instant even when the original filename was imprecise.
    """
    folder_path = Path(folder)
    posters_dir = Path(settings.POSTERS_DIR)

    def _check_cached(key: str) -> Optional[Path]:
        safe = _safe(key)
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            p = posters_dir / f"{safe}{ext}"
            if p.exists() and p.is_file():
                return p
        return None

    # 1. Check cache — input key first, then bare folder name
    input_key   = f"{title} ({year})" if year else title
    folder_name = folder_path.name
    for key in (input_key, folder_name):
        hit = _check_cached(key)
        if hit:
            return FileResponse(str(hit))

    # 2. Legacy: poster.jpg / folder.jpg stored inside the media folder
    for name in _POSTER_NAMES:
        p = folder_path / name
        if p.exists() and p.is_file():
            return FileResponse(str(p))

    # 3. Resolve via TMDB using the shared authenticated client
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

    # 5. Cache under the canonical key so future requests hit the cache
    canonical_key = f"{canonical_title} ({canonical_year})" if canonical_year else canonical_title
    try:
        posters_dir.mkdir(parents=True, exist_ok=True)
        cache_file = posters_dir / f"{_safe(canonical_key)}.jpg"
        cache_file.write_bytes(poster_data)
        logger.info("Cached TMDB poster '%s' → %s", canonical_key, cache_file.name)
    except Exception as exc:
        logger.warning("Could not cache poster for '%s': %s", canonical_key, exc)

    return Response(content=poster_data, media_type="image/jpeg")


# ── Folder normalizer ─────────────────────────────────────────────────────────

def _safe_folder(name: str) -> str:
    """Make a title safe for use as a Windows/macOS folder name.

    Replaces ``': '`` → ``' - '`` (preserves readability for subtitles like
    "Thor: Love and Thunder") then strips the remaining illegal characters.
    """
    name = re.sub(r":\s*", " - ", name)          # "Thor: Love…" → "Thor - Love…"
    name = re.sub(r'[\\/*?"<>|]', "", name)       # strip remaining illegals
    return name.strip(" .")


@router.post("/library/normalize")
async def normalize_library(dry_run: bool = True):
    """Rename media folders to canonical ``Title (Year)`` form using TMDB.

    Queries TMDB for each folder in all configured library directories and
    proposes (``dry_run=true``) or executes (``dry_run=false``) renames.

    Only *subdirectories* are renamed — individual video files are never
    touched.  Already-canonical folders (name unchanged) are skipped.

    Returns::

        {
            "dry_run": true,
            "proposals": [{"old": "...", "new": "...", "path": "..."}, …],
            "renamed":   [],   // populated when dry_run=false
            "skipped":   […],  // already correct / flat files / TMDB miss
            "errors":    […],
        }
    """
    if not state.tmdb:
        raise HTTPException(status_code=503, detail="TMDB client not initialised")

    cfg = settings
    lib_dirs = [
        (cfg.MOVIES_DIR,         "movie"),
        (cfg.TV_DIR,             "tv"),
        (cfg.ANIME_DIR,          "anime"),
        (cfg.MOVIES_DIR_ARCHIVE, "movie"),
        (cfg.TV_DIR_ARCHIVE,     "tv"),
        (cfg.ANIME_DIR_ARCHIVE,  "anime"),
    ]

    proposals: list[dict] = []
    skipped:   list[str]  = []
    errors:    list[str]  = []

    for lib_path_str, media_type in lib_dirs:
        lib_path = Path(lib_path_str)
        if not lib_path.exists():
            continue

        for entry in sorted(lib_path.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            current_name = entry.name
            parsed_title, parsed_year = _extract_title_year(current_name)

            try:
                canonical_title, canonical_year, _ = await state.tmdb.fuzzy_resolve(
                    parsed_title, media_type=media_type, year=parsed_year
                )
            except Exception as exc:
                skipped.append(f"{current_name}: TMDB miss — {exc}")
                continue

            if not canonical_year:
                canonical_year = parsed_year

            new_name = _safe_folder(
                f"{canonical_title} ({canonical_year})" if canonical_year
                else canonical_title
            )

            if new_name == current_name:
                skipped.append(f"{current_name}: already canonical")
                continue

            proposals.append({
                "old":  current_name,
                "new":  new_name,
                "path": str(entry),
            })

    renamed: list[dict] = []

    if not dry_run:
        for prop in proposals:
            old_path = Path(prop["path"])
            new_path = old_path.parent / prop["new"]
            try:
                if new_path.exists():
                    errors.append(
                        f"Skipped '{prop['old']}' → '{prop['new']}': destination already exists"
                    )
                    continue
                old_path.rename(new_path)
                renamed.append(prop)
                logger.info("Renamed: '%s' → '%s'", prop["old"], prop["new"])
            except Exception as exc:
                errors.append(f"Failed to rename '{prop['old']}': {exc}")

        # Rescan so the UI reflects the new names
        if state.library and renamed:
            state.library.scan(force=True)

    return {
        "dry_run":   dry_run,
        "proposals": proposals if dry_run else [],
        "renamed":   renamed,
        "skipped":   skipped,
        "errors":    errors,
    }


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
