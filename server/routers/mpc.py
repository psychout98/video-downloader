"""
MPC-BE player proxy endpoints.

GET  /api/mpc/status    Current player state + resolved media context
GET  /api/mpc/stream    SSE push stream of player state
POST /api/mpc/command   Send a wm_command to MPC-BE
POST /api/mpc/open      Open a file by tmdb_id + rel_path (or raw path)
POST /api/mpc/next      Skip to next episode
POST /api/mpc/prev      Go to previous episode
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import state
from ..config import settings

router = APIRouter(prefix="/api/mpc", tags=["mpc"])
logger = logging.getLogger(__name__)


# ── Request models ────────────────────────────────────────────────────────────

class MPCCommandRequest(BaseModel):
    command:     int
    position_ms: Optional[int] = None   # only used for seek (wm_command 889)

class MPCOpenRequest(BaseModel):
    tmdb_id:  int
    rel_path: str
    playlist: Optional[list[str]] = None   # full episode playlist for autoplay


# ── Regex patterns ───────────────────────────────────────────────────────────

_EP_RE = re.compile(r"[Ss](\d+)[Ee](\d+)")
_TMDB_ID_RE = re.compile(r"\[(\d+)\]")
_VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv", ".m4v"}


# ── Media context resolution ────────────────────────────────────────────────

def _resolve_media_context(file_path: str) -> dict | None:
    """Extract tmdb_id from [id] in file path and resolve media context.

    Parses the path for a [tmdb_id] bracket pattern and SxEx episode info.
    Looks up the library for title/type metadata.
    """
    if not file_path:
        return None

    # Extract tmdb_id from [N] pattern in the path
    m_id = _TMDB_ID_RE.search(file_path)
    if not m_id:
        return None

    tmdb_id = int(m_id.group(1))

    # Extract season/episode from SxEx pattern
    season, episode = None, None
    m_ep = _EP_RE.search(file_path)
    if m_ep:
        season = int(m_ep.group(1))
        episode = int(m_ep.group(2))

    # Look up library for title/type
    title = ""
    media_type = ""
    items = []
    if state.library:
        try:
            items = state.library.scan()
        except Exception:
            pass

    for item in items:
        if item.get("tmdb_id") == tmdb_id:
            title = item.get("title", "")
            media_type = item.get("type", "")
            break

    poster_url = f"/api/library/{tmdb_id}/poster"

    return {
        "tmdb_id":    tmdb_id,
        "title":      title,
        "type":       media_type,
        "poster_url": poster_url,
        "season":     season,
        "episode":    episode,
    }


def _strip_windows_paths(media: dict | None) -> dict | None:
    """Remove raw Windows drive-letter paths from media context."""
    if media is None:
        return None
    cleaned = {}
    for k, v in media.items():
        if isinstance(v, str) and re.match(r"^[A-Z]:\\", v):
            cleaned[k] = None
        else:
            cleaned[k] = v
    return cleaned


# ── File resolution helpers ───────────────────────────────────────────────────

def _resolve_file_path(tmdb_id: int, rel_path: str) -> str | None:
    """Resolve tmdb_id + rel_path to an absolute file path string.

    Searches MEDIA_DIR and ARCHIVE_DIR for the folder matching tmdb_id
    from the library, then checks for the file inside.
    """
    # Get folder_name from library
    folder_name = None
    items = []
    if state.library:
        try:
            items = state.library.scan()
        except Exception:
            pass

    for item in items:
        if item.get("tmdb_id") == tmdb_id:
            folder_name = item.get("folder_name")
            break

    if not folder_name:
        return None

    # Search in MEDIA_DIR and ARCHIVE_DIR
    for base_dir in (settings.MEDIA_DIR, settings.ARCHIVE_DIR):
        candidate = Path(base_dir) / folder_name / rel_path
        if candidate.is_file():
            return str(candidate)

    return None


def _get_adjacent_episode(current_file: str, offset: int) -> str | None:
    """Find the next (+1) or previous (-1) episode in the same folder.

    Returns the absolute path as a string, or None if not found.
    Only considers video files, sorted by name.
    """
    if not current_file:
        return None

    current = Path(current_file)
    folder = current.parent

    if not folder.is_dir():
        return None

    # Collect sorted video files in the same directory
    videos = sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in _VIDEO_EXTS
    )

    if not videos:
        return None

    # Find current file index
    current_idx = None
    for i, v in enumerate(videos):
        if v.name == current.name:
            current_idx = i
            break

    if current_idx is None:
        return None

    target_idx = current_idx + offset
    if target_idx < 0 or target_idx >= len(videos):
        return None

    return str(videos[target_idx])


# ── Legacy helpers (used by endpoints) ────────────────────────────────────────

def _find_library_folder(tmdb_id: int) -> Path | None:
    """Find the library folder for a given tmdb_id by scanning known dirs."""
    search_dirs = [
        settings.MEDIA_DIR, settings.ARCHIVE_DIR,
    ]
    # Also check legacy dirs if they exist
    for attr in ("MOVIES_DIR", "TV_DIR", "ANIME_DIR",
                 "MOVIES_DIR_ARCHIVE", "TV_DIR_ARCHIVE", "ANIME_DIR_ARCHIVE"):
        d = getattr(settings, attr, None)
        if d and d not in search_dirs:
            search_dirs.append(d)

    for d in search_dirs:
        parent = Path(d)
        if not parent.is_dir():
            continue
        for folder in parent.iterdir():
            if folder.is_dir() and f"[{tmdb_id}]" in folder.name:
                return folder
    return None


def _resolve_episode_path(tmdb_id: int, rel_path: str) -> Path | None:
    """Resolve tmdb_id + rel_path to an absolute file path."""
    folder = _find_library_folder(tmdb_id)
    if folder is None:
        return None
    full = folder / rel_path
    if full.is_file():
        return full
    # Search recursively
    for f in folder.rglob(Path(rel_path).name):
        if f.is_file():
            return f
    return None


def _get_episodes_in_folder(folder: Path) -> list[Path]:
    """Return sorted list of video files in a show folder."""
    eps = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.suffix.lower() in _VIDEO_EXTS and _EP_RE.search(f.name):
            eps.append(f)
    return eps


def _find_adjacent_episode(current_file: str, offset: int) -> tuple[Path | None, str | None]:
    """Find the next (+1) or previous (-1) episode relative to current_file.

    Returns (absolute_path, rel_path_from_show_folder) or (None, None).
    """
    current = Path(current_file)
    # Walk up to find the show folder (contains [tmdb_id])
    show_folder = None
    for parent in current.parents:
        if re.search(r"\[\d+\]", parent.name):
            show_folder = parent
            break
    if show_folder is None:
        # Try parent of parent (e.g. Show/Season 1/ep.mkv)
        if current.parent.parent.is_dir():
            show_folder = current.parent.parent
        else:
            return None, None

    episodes = _get_episodes_in_folder(show_folder)
    if not episodes:
        return None, None

    # Find current index
    current_idx = None
    for i, ep in enumerate(episodes):
        if ep.resolve() == current.resolve() or ep.name == current.name:
            current_idx = i
            break

    if current_idx is None:
        return None, None

    target_idx = current_idx + offset
    if target_idx < 0 or target_idx >= len(episodes):
        return None, None

    target = episodes[target_idx]
    try:
        rel = str(target.relative_to(show_folder))
    except ValueError:
        rel = target.name
    return target, rel


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def mpc_status():
    status_obj = await state.mpc.get_status()
    result = status_obj.to_dict()

    # Resolve media context from the currently playing file
    media = _resolve_media_context(result.get("file", ""))
    result["media"] = _strip_windows_paths(media)
    return result


@router.post("/command")
async def mpc_command(body: MPCCommandRequest):
    extra = {}
    if body.position_ms is not None:
        extra["position"] = body.position_ms
    ok = await state.mpc.command(body.command, **extra)
    return {"ok": ok}


@router.post("/open")
async def mpc_open(body: MPCOpenRequest):
    """Open a file in MPC-BE by resolving tmdb_id + rel_path."""
    # Try the library-aware resolution first
    resolved_str = _resolve_file_path(body.tmdb_id, body.rel_path)
    resolved = Path(resolved_str) if resolved_str else None

    # Fall back to legacy resolution
    if resolved is None:
        resolved = _resolve_episode_path(body.tmdb_id, body.rel_path)

    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"File not found: tmdb_id={body.tmdb_id}, rel_path={body.rel_path}",
        )

    exe = settings.MPC_BE_EXE
    if not Path(exe).exists():
        raise HTTPException(
            status_code=500,
            detail=f"MPC-BE executable not found at '{exe}'. Set MPC_BE_EXE in .env.",
        )

    # Build playlist if provided
    if body.playlist and len(body.playlist) > 1:
        playlist_paths = []
        for rel in body.playlist:
            p_str = _resolve_file_path(body.tmdb_id, rel)
            if not p_str:
                p = _resolve_episode_path(body.tmdb_id, rel)
                p_str = str(p) if p else rel
            playlist_paths.append(p_str)
        open_path = _make_playlist(playlist_paths)
    else:
        open_path = str(resolved)

    was_running = await state.mpc.ping()

    try:
        subprocess.Popen(
            [exe, open_path],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch MPC-BE: {exc}")

    return {"ok": True, "launched": not was_running}


@router.post("/next")
async def mpc_next():
    """Skip to the next episode based on what's currently playing."""
    status_obj = await state.mpc.get_status()
    current_file = status_obj.file if hasattr(status_obj, "file") else ""
    if not current_file:
        raise HTTPException(status_code=404, detail="Nothing is currently playing")

    # Try simple adjacent episode first (same folder)
    adjacent = _get_adjacent_episode(current_file, +1)
    if adjacent:
        rel_path = Path(adjacent).name
        return {"ok": True, "rel_path": rel_path, "path": adjacent}

    # Fall back to show-folder-aware resolution
    target, rel_path = _find_adjacent_episode(current_file, +1)
    if target is None:
        raise HTTPException(status_code=404, detail="No next episode found")

    return {"ok": True, "rel_path": rel_path, "path": str(target)}


@router.post("/prev")
async def mpc_prev():
    """Go to the previous episode based on what's currently playing."""
    status_obj = await state.mpc.get_status()
    current_file = status_obj.file if hasattr(status_obj, "file") else ""
    if not current_file:
        raise HTTPException(status_code=404, detail="Nothing is currently playing")

    # Try simple adjacent episode first (same folder)
    adjacent = _get_adjacent_episode(current_file, -1)
    if adjacent:
        rel_path = Path(adjacent).name
        return {"ok": True, "rel_path": rel_path, "path": adjacent}

    # Fall back to show-folder-aware resolution
    target, rel_path = _find_adjacent_episode(current_file, -1)
    if target is None:
        raise HTTPException(status_code=404, detail="No previous episode found")

    return {"ok": True, "rel_path": rel_path, "path": str(target)}


@router.get("/stream")
async def mpc_stream(limit: int = 0):
    """SSE endpoint that pushes player status updates.

    Args:
        limit: If > 0, stop after emitting this many events (useful for testing).
               Default 0 means stream indefinitely.
    """

    async def event_generator():
        count = 0
        while True:
            try:
                status_obj = await state.mpc.get_status()
                result = status_obj.to_dict()
                media = _resolve_media_context(result.get("file", ""))
                result["media"] = _strip_windows_paths(media)
                yield f"data:{json.dumps(result)}\n\n"
            except Exception:
                yield f"data:{json.dumps({'reachable': False, 'state': 0, 'media': None})}\n\n"
            count += 1
            if limit and count >= limit:
                return
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_playlist(files: list[str]) -> str:
    """Write a temporary .m3u playlist and return its path as a string."""
    playlist_file = state.ROOT_DIR / "data" / "current_playlist.m3u"
    playlist_file.parent.mkdir(parents=True, exist_ok=True)
    with open(playlist_file, "w", encoding="utf-8-sig") as fh:
        fh.write("#EXTM3U\n")
        for p in files:
            fh.write(p + "\n")
    return str(playlist_file)
