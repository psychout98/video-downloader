"""
System / server management endpoints.

GET  /api/status    Server health + config summary
GET  /api/logs      Tail the server log file
POST /api/shutdown  Gracefully stop the server process
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

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
        "auth_enabled":       settings.SECRET_KEY != "change-me",
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


@router.post("/shutdown")
async def api_shutdown():
    """Gracefully stop the server process."""
    logger.info("Shutdown requested via API")

    async def _do_shutdown():
        await asyncio.sleep(0.3)   # let the response be sent first
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_do_shutdown())
    return {"ok": True, "message": "Server shutting down…"}


@router.post("/restart")
async def api_restart():
    """Restart the server by spawning a fresh child process then exiting."""
    logger.info("Restart requested via API")

    async def _do_restart():
        await asyncio.sleep(0.4)   # let the response be sent first
        import subprocess
        # Reconstruct as "python -m uvicorn <args>" to avoid sys.argv[0] being
        # the uvicorn __main__.py path, which would shadow stdlib logging.
        cmd = [sys.executable, "-m", "uvicorn"] + sys.argv[1:]
        kwargs: dict = {"cwd": os.getcwd(), "env": os.environ.copy()}
        if sys.platform == "win32":
            # Detach from the current console so the child outlives the parent
            DETACHED_PROCESS         = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            kwargs["creationflags"]  = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, **kwargs)
        os._exit(0)   # terminate this process; child carries on independently

    asyncio.create_task(_do_restart())
    return {"ok": True, "message": "Server restarting…"}
