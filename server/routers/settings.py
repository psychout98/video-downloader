"""
Application settings endpoints.

GET  /api/settings   Read current values from the live settings object
POST /api/settings   Persist updated values to .env (requires server restart)
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import state
from ..config import settings, reload_settings

router = APIRouter(prefix="/api", tags=["settings"])

# Keys exposed through the settings API
_SETTINGS_KEYS = [
    "TMDB_API_KEY", "REAL_DEBRID_API_KEY", "SECRET_KEY",
    "MOVIES_DIR", "TV_DIR", "ANIME_DIR",
    "MOVIES_DIR_ARCHIVE", "TV_DIR_ARCHIVE", "ANIME_DIR_ARCHIVE",
    "DOWNLOADS_DIR", "POSTERS_DIR", "PROGRESS_FILE",
    "MPC_BE_URL", "MPC_BE_EXE",
    "WATCH_THRESHOLD", "HOST", "PORT", "MAX_CONCURRENT_DOWNLOADS",
]


class SettingsUpdateRequest(BaseModel):
    updates: dict   # {KEY: new_value_str}


@router.get("/settings")
async def get_settings():
    """Return current setting values from the live settings object."""
    return {
        key: (getattr(settings, key, None) or "")
        for key in _SETTINGS_KEYS
    }


@router.post("/settings")
async def update_settings(body: SettingsUpdateRequest):
    """Persist updated values to .env using python-dotenv.
    The server must be restarted for changes to take effect."""
    from dotenv import set_key as _set_key

    if not state.ENV_FILE.exists():
        state.ENV_FILE.touch()

    written: list[str] = []
    errors:  list[str] = []

    for key, value in body.updates.items():
        if key not in _SETTINGS_KEYS:
            errors.append(f"Unknown key: {key}")
            continue
        try:
            # Strip surrounding quotes the user may have accidentally pasted
            clean = str(value).strip().strip("'\"")
            _set_key(str(state.ENV_FILE), key, clean)
            written.append(key)
        except Exception as exc:
            errors.append(f"{key}: {exc}")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Hot-reload the settings object so new values take effect immediately
    reload_settings()
    _reinit_clients()

    return {
        "ok":      True,
        "written": written,
        "note":    "Settings applied. A restart is only needed for HOST/PORT changes.",
    }


@router.get("/settings/test-rd")
async def test_rd_key():
    """Test the current in-memory Real-Debrid API key and return its status."""
    key = settings.REAL_DEBRID_API_KEY
    masked = f"…{key[-6:]}" if len(key) >= 6 else "(too short)"
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                "https://api.real-debrid.com/rest/1.0/user",
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code == 200:
            username = r.json().get("username", "?")
            return {"ok": True,  "key_suffix": masked, "username": username}
        return {"ok": False, "key_suffix": masked,
                "error": f"RD returned HTTP {r.status_code}"}
    except Exception as exc:
        return {"ok": False, "key_suffix": masked, "error": str(exc)}


def _reinit_clients() -> None:
    """Reinitialise API-key-bearing clients after a settings reload.

    Also updates the JobProcessor's references since it holds pointers
    to the old singleton instances.
    """
    from ..clients.tmdb_client       import TMDBClient
    from ..clients.torrentio_client  import TorrentioClient
    from ..clients.realdebrid_client import RealDebridClient

    if state.tmdb is not None:
        state.tmdb = TMDBClient(settings.TMDB_API_KEY)
    if state.torrentio is not None:
        state.torrentio = TorrentioClient(settings.REAL_DEBRID_API_KEY)
    if state.rd is not None:
        state.rd = RealDebridClient(settings.REAL_DEBRID_API_KEY, poll_interval=settings.RD_POLL_INTERVAL)

    # Re-point the processor to the new singleton instances
    if state.processor is not None:
        state.processor._tmdb = state.tmdb
        state.processor._torrentio = state.torrentio
        state.processor._rd = state.rd
