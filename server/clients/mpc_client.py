"""
MPC-BE web interface client.

Setup on HTPC
-------------
MPC-BE → View → Options → Player → Web Interface
  ☑ Listen on port:  13579
  (leave "Allow access from localhost only" UNCHECKED so the iPad can reach it)

API endpoints used
------------------
GET /variables.html   → current player state (JSON or legacy JS-variable format)
GET /command.html     → send a command via ?wm_command=N (and optional params)

Key command IDs
---------------
  887  Play/Pause toggle
  888  Stop
  891  Play
  892  Pause
  907  Volume +5%
  908  Volume -5%
  909  Mute toggle
  889  Seek  (also pass &position=<milliseconds>)
   -1  Open file  (also pass &path=<url-encoded Windows path>)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
import urllib.parse

import httpx

logger = logging.getLogger(__name__)


class MPCStatus:
    def __init__(self, data: dict, reachable: bool = True):
        self._d       = data
        self.reachable = reachable

    @property
    def file(self) -> str:
        return self._d.get("file", "") or self._d.get("filepath", "")

    @property
    def filename(self) -> str:
        return self._d.get("filename", "") or (self.file.split("\\")[-1] if "\\" in self.file else self.file.split("/")[-1])

    @property
    def state(self) -> int:
        """0=stopped, 1=paused, 2=playing"""
        v = self._d.get("state", 0)
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @property
    def is_playing(self) -> bool:
        return self.state == 2

    @property
    def is_paused(self) -> bool:
        return self.state == 1

    @property
    def position_ms(self) -> int:
        v = self._d.get("position", 0)
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @property
    def duration_ms(self) -> int:
        v = self._d.get("duration", 0)
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @property
    def position_str(self) -> str:
        return self._d.get("positionstring", _ms_to_str(self.position_ms))

    @property
    def duration_str(self) -> str:
        return self._d.get("durationstring", _ms_to_str(self.duration_ms))

    @property
    def volume(self) -> int:
        v = self._d.get("volumelevel", 100)
        try:
            return int(v)
        except (ValueError, TypeError):
            return 100

    @property
    def muted(self) -> bool:
        v = self._d.get("muted", False)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("1", "true", "yes")

    def to_dict(self) -> dict:
        return {
            "reachable":   self.reachable,
            "file":        self.file,
            "filename":    self.filename,
            "state":       self.state,
            "is_playing":  self.is_playing,
            "is_paused":   self.is_paused,
            "position_ms": self.position_ms,
            "duration_ms": self.duration_ms,
            "position_str": self.position_str,
            "duration_str": self.duration_str,
            "volume":      self.volume,
            "muted":       self.muted,
        }


class MPCClient:
    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")

    async def get_status(self) -> MPCStatus:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{self._base}/variables.html")
                r.raise_for_status()
                parsed = self._parse_variables(r.text)
                return MPCStatus(parsed, reachable=True)
        except Exception as exc:
            logger.debug("MPC-BE unreachable at %s: %s", self._base, exc)
            return MPCStatus({}, reachable=False)

    async def command(self, wm_command: int, **extra_params) -> bool:
        params: dict[str, Any] = {"wm_command": wm_command, **extra_params}
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{self._base}/command.html", params=params)
                return r.status_code in (200, 201, 204)
        except Exception as exc:
            logger.debug("MPC-BE command %d failed: %s", wm_command, exc)
            return False

    async def play_pause(self) -> bool:
        return await self.command(887)

    async def play(self) -> bool:
        return await self.command(891)

    async def pause(self) -> bool:
        return await self.command(892)

    async def stop(self) -> bool:
        return await self.command(888)

    async def mute(self) -> bool:
        return await self.command(909)

    async def volume_up(self) -> bool:
        return await self.command(907)

    async def volume_down(self) -> bool:
        return await self.command(908)

    async def seek(self, position_ms: int) -> bool:
        return await self.command(889, position=position_ms)

    async def ping(self) -> bool:
        """Return True if MPC-BE's web interface is reachable (i.e. the process is running)."""
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(f"{self._base}/variables.html")
                return r.status_code == 200
        except Exception:
            return False

    async def open_file(self, path: str) -> bool:
        """
        Open a file in MPC-BE.
        *path* should be the local Windows path on the HTPC, e.g.
        'D:\\Media\\Movies\\Inception (2010)\\Inception (2010).mkv'
        """
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    f"{self._base}/command.html",
                    params={"wm_command": -1, "path": path},
                )
                return r.status_code in (200, 201, 204)
        except Exception as exc:
            logger.warning("MPC-BE open_file failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Variable parsing (handles both JSON and legacy JS format)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_variables(text: str) -> dict:
        # Try JSON first (newer MPC-BE versions)
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                import json
                return json.loads(stripped)
            except Exception:
                pass

        # Legacy JS format: OnVariable("key","value");
        result: dict = {}
        for m in re.finditer(r'OnVariable\("([^"]+)","([^"]*)"\)', text):
            result[m.group(1)] = m.group(2)
        if result:
            return result

        # HTML format: <p id="key">value</p>  (current MPC-BE default)
        for m in re.finditer(r'<p\s+id="([^"]+)">([^<]*)</p>', text):
            key, val = m.group(1), m.group(2).strip()
            # filepatharg is URL-encoded; also expose it as "filepath"
            if key == "filepatharg":
                result["filepath"] = urllib.parse.unquote(val)
            result[key] = val
        return result


def _ms_to_str(ms: int) -> str:
    if not ms:
        return "0:00"
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"
