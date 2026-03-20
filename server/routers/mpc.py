"""
MPC-BE player proxy endpoints.

GET  /api/mpc/status    Current player state (file, position, volume…)
POST /api/mpc/command   Send a wm_command to MPC-BE
POST /api/mpc/open      Open a file (or playlist) in MPC-BE
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
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
    path:     str
    playlist: Optional[list[str]] = None   # full episode playlist for autoplay


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def mpc_status():
    status_obj = await state.mpc.get_status()
    return status_obj.to_dict()


@router.post("/command")
async def mpc_command(body: MPCCommandRequest):
    extra = {}
    if body.position_ms is not None:
        extra["position"] = body.position_ms
    ok = await state.mpc.command(body.command, **extra)
    return {"ok": ok}


@router.post("/open")
async def mpc_open(body: MPCOpenRequest):
    """Open a file or playlist in MPC-BE.

    Always uses ``subprocess.Popen`` to launch/reuse MPC-BE rather than the
    web API ``/command.html`` endpoint — the web API returns HTTP 200 even
    when the command is silently ignored, making it unreliable for file open.

    When MPC-BE is in single-instance mode (default), passing a file path to
    the executable a second time causes the existing window to open that file.

    Returns ``{"ok": true, "launched": true}`` if MPC-BE had to be started
    from scratch, or ``{"ok": true, "launched": false}`` if it was already
    running.  The UI uses ``launched`` to decide how long to wait before
    polling the Now Playing tab.
    """
    exe = settings.MPC_BE_EXE
    if not Path(exe).exists():
        raise HTTPException(
            status_code=500,
            detail=(
                f"MPC-BE executable not found at '{exe}'. "
                "Set MPC_BE_EXE in your .env file."
            ),
        )

    # Build a .m3u playlist file when multiple episodes are provided so
    # MPC-BE autoplays through the season after the current episode finishes.
    files     = body.playlist if (body.playlist and len(body.playlist) > 1) else [body.path]
    open_path = _make_playlist(files) if len(files) > 1 else files[0]

    # Ping first so we can report whether a new instance was launched
    was_running = await state.mpc.ping()

    try:
        subprocess.Popen(
            [exe, open_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch MPC-BE: {exc}")

    return {"ok": True, "launched": not was_running}


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
