"""
Media Downloader — FastAPI application entry point.

Endpoints are split into focused router modules under server/routers/:
  jobs.py      — /api/search, /api/download, /api/jobs/*
  library.py   — /api/library*, /api/progress
  mpc.py       — /api/mpc/*
  settings.py  — /api/settings
  system.py    — /api/status, /api/logs

External API wrappers live in server/clients/:
  mpc_client, realdebrid_client, tmdb_client, torrentio_client

Business logic lives in server/core/:
  job_processor, library_manager, media_organizer,
  progress_store, watch_tracker

App-level singleton instances live in server/state.py and are populated
during lifespan() before the first request arrives.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import state
from .config import settings
from .database import init_db
from .clients.mpc_client import MPCClient
from .clients.realdebrid_client import RealDebridClient
from .clients.tmdb_client import TMDBClient
from .clients.torrentio_client import TorrentioClient
from .core.job_processor import JobProcessor
from .core.library_manager import LibraryManager
from .core.progress_store import ProgressStore
from .core.watch_tracker import WatchTracker

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
_file_log_handler: Optional[logging.FileHandler] = None


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _file_log_handler

    # File logging
    try:
        state.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _file_log_handler = logging.FileHandler(state.LOG_FILE, encoding="utf-8")
        _file_log_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logging.getLogger().addHandler(_file_log_handler)
    except Exception as exc:
        logger.warning("Could not set up file logging: %s", exc)

    # PID file (used by stop_server.bat)
    try:
        state.PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    except Exception as exc:
        logger.warning("Could not write PID file: %s", exc)

    # Ensure data directory exists
    state.DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Media Downloader starting …")
    await init_db()

    # Populate shared singletons so routers can use them
    state.tmdb           = TMDBClient(settings.TMDB_API_KEY)
    state.torrentio      = TorrentioClient(settings.REAL_DEBRID_API_KEY)
    state.rd             = RealDebridClient(settings.REAL_DEBRID_API_KEY, poll_interval=settings.RD_POLL_INTERVAL)
    state.library        = LibraryManager()
    state.mpc            = MPCClient(settings.MPC_BE_URL)
    state.progress_store = ProgressStore(settings.PROGRESS_FILE)
    state.processor      = JobProcessor()
    state.processor.start()
    state.watch_tracker  = WatchTracker(state.mpc, state.progress_store)
    state.watch_tracker.start()

    # Auto-refresh library on startup (background task)
    asyncio.create_task(_startup_library_refresh())

    yield   # ← server is live

    if state.watch_tracker:  state.watch_tracker.stop()
    if state.processor:      state.processor.stop()
    if state.tmdb:           await state.tmdb.close()
    if state.torrentio:      await state.torrentio.close()
    if state.rd:             await state.rd.close()

    logger.info("Media Downloader stopped")

    try:
        state.PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    if _file_log_handler:
        logging.getLogger().removeHandler(_file_log_handler)
        _file_log_handler.close()


async def _startup_library_refresh():
    """Run library scan + smart refresh in background on startup."""
    try:
        # Initial scan (fast, no TMDB calls)
        state.library.scan(force=True)
        logger.info("Startup library scan complete")
    except Exception as exc:
        logger.warning("Startup library scan failed: %s", exc)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Media Downloader", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from .routers import jobs, library, mpc, settings as settings_router, system

app.include_router(jobs.router)
app.include_router(library.router)
app.include_router(mpc.router)
app.include_router(settings_router.router)
app.include_router(system.router)


# ── Static files + UI ─────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def ui_root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Frontend not built. Run: cd frontend && npm run build"}, status_code=503)


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


# SPA fallback: serve index.html for any unmatched non-API route
@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    # Serve static file if it exists
    static_file = STATIC_DIR / path
    if static_file.exists() and static_file.is_file():
        return FileResponse(static_file)
    # Otherwise serve index.html for client-side routing
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Not found"}, status_code=404)


# ── Fallback error handler ────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    logger.error("Unhandled: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
