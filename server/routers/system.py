"""
System endpoints.

GET  /api/status    Server health + config summary
GET  /api/logs      Tail the server log file

Note: shutdown and restart have been moved to the system tray app
(tray/tray_app.py) since browser-based service management is unreliable.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .. import state
from ..config import settings

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def server_status():
    return {
        "status":             "ok",
        "movies_dir":         settings.MOVIES_DIR,
        "tv_dir":             settings.TV_DIR,
        "anime_dir":          settings.ANIME_DIR,
        "movies_dir_archive": settings.MOVIES_DIR_ARCHIVE,
        "tv_dir_archive":     settings.TV_DIR_ARCHIVE,
        "anime_dir_archive":  settings.ANIME_DIR_ARCHIVE,
        "watch_threshold_pct": int(settings.WATCH_THRESHOLD * 100),
        "mpc_be_url":         settings.MPC_BE_URL,
    }


@router.get("/logs")
async def get_logs(lines: int = 200):
    """Return the last *lines* lines from the server log file."""
    if not state.LOG_FILE.exists():
        return {
            "lines": [],
            "note":  "No log file found — server may not have been started via the normal launcher.",
        }
    try:
        with open(state.LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = [ln.rstrip() for ln in all_lines[-lines:]]
        return {"lines": tail, "total": len(all_lines)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read log: {exc}")
