"""
Application settings endpoints.

GET  /api/settings   Read current values from the live settings object
POST /api/settings   Persist updated values to .env (requires server restart)
"""
from __future__ import annotations

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
            _set_key(str(state.ENV_FILE), key, str(value))
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


def _reinit_clients() -> None:
    """Reinitialise API-key-bearing clients after a settings reload."""
    from ..clients.tmdb_client      import TMDBClient
    from ..clients.torrentio_client import TorrentioClient

    if state.tmdb is not None:
        state.tmdb = TMDBClient(settings.TMDB_API_KEY)
    if state.torrentio is not None:
        state.torrentio = TorrentioClient(settings.REAL_DEBRID_API_KEY)
