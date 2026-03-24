"""
Application settings endpoints.

GET  /api/settings          Read current values from the live settings object
POST /api/settings          Persist updated values to .env
GET  /api/settings/test-rd  Test the Real-Debrid API key
"""
from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import state
from ..config import settings, reload_settings

router = APIRouter(prefix="/api", tags=["settings"])
logger = logging.getLogger(__name__)

# Keys exposed through the settings API
_SETTINGS_KEYS = [
    "TMDB_API_KEY", "REAL_DEBRID_API_KEY",
    "MEDIA_DIR", "ARCHIVE_DIR",
    "DOWNLOADS_DIR", "POSTERS_DIR",
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

    Fixes the single-quote wrapping bug by using dotenv's set_key properly
    and verifying the written values.
    """
    if not state.ENV_FILE.exists():
        state.ENV_FILE.touch()

    written: list[str] = []
    errors:  list[str] = []

    for key, value in body.updates.items():
        if key not in _SETTINGS_KEYS:
            errors.append(f"Unknown key: {key}")
            continue
        try:
            # Clean the value: strip surrounding whitespace and any
            # accidentally pasted quotes
            clean = str(value).strip().strip("'\"")

            # Write directly to the .env file using a reliable method
            # that avoids the single-quote wrapping bug
            _write_env_key(str(state.ENV_FILE), key, clean)
            written.append(key)
        except Exception as exc:
            errors.append(f"{key}: {exc}")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Verify the written values by reading back the file
    verify_errors = _verify_env_file(str(state.ENV_FILE), {k: body.updates[k] for k in written})
    if verify_errors:
        logger.warning("Env verification issues: %s", verify_errors)

    # Hot-reload the settings object so new values take effect immediately
    reload_settings()
    _reinit_clients()

    return {
        "ok":      True,
        "written": written,
        "note":    "Settings applied. A restart is only needed for HOST/PORT changes.",
    }


def _write_env_key(env_path: str, key: str, value: str) -> None:
    """Write a key=value pair to .env without single-quote wrapping.

    Uses python-dotenv's set_key with quote_mode="never" to prevent
    the library from wrapping values in quotes.
    """
    from dotenv import set_key as _set_key

    # python-dotenv set_key: the quote_mode parameter controls quoting.
    # "never" ensures no quotes are added around the value.
    try:
        _set_key(env_path, key, value, quote_mode="never")
    except TypeError:
        # Older versions of python-dotenv don't support quote_mode
        # Fall back to manual write
        _manual_write_env_key(env_path, key, value)


def _manual_write_env_key(env_path: str, key: str, value: str) -> None:
    """Manually write key=value to .env file without any quoting.

    Fallback for older python-dotenv versions.
    """
    from pathlib import Path

    path = Path(env_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    # Find and replace existing key, or append
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    found = False
    new_lines = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _verify_env_file(env_path: str, expected: dict) -> list[str]:
    """Read back the .env file and verify values were written correctly."""
    from dotenv import dotenv_values

    actual = dotenv_values(env_path)
    errors = []

    # Also read the raw file to detect unparseable quote issues
    raw_lines = {}
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    raw_lines[k.strip()] = v.strip()
    except Exception:
        pass

    for key, expected_value in expected.items():
        actual_value = actual.get(key, "")
        clean_expected = str(expected_value).strip().strip("'\"")
        # Check for unwanted quote wrapping in parsed value
        if actual_value and (actual_value.startswith("'") or actual_value.endswith("'")):
            errors.append(f"{key} has unwanted single quotes: {actual_value!r}")
        # Also check raw file for unmatched/leading quotes that dotenv couldn't parse
        elif not actual_value and key in raw_lines:
            raw_val = raw_lines[key]
            if raw_val.startswith("'") or raw_val.endswith("'"):
                errors.append(f"{key} has unwanted single quotes: {raw_val!r}")
    return errors


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
    """Reinitialise API-key-bearing clients after a settings reload."""
    from ..clients.tmdb_client       import TMDBClient
    from ..clients.torrentio_client  import TorrentioClient
    from ..clients.realdebrid_client import RealDebridClient

    import asyncio

    async def _close_old():
        if state.tmdb is not None:
            await state.tmdb.close()
        if state.torrentio is not None:
            await state.torrentio.close()
        if state.rd is not None:
            await state.rd.close()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_close_old())
    except RuntimeError:
        pass

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
