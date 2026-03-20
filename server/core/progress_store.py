"""
Persistent watch-progress store.

Stores per-file playback position so users can resume episodes and the UI can
show per-episode progress bars.

Data is kept in a single JSON file (default: %USERPROFILE%\\Media\\progress.json):

    {
      "C:\\Media\\TV Shows\\Show\\Season 01\\ep.mkv": {
          "position_ms": 1234,
          "duration_ms": 3600000,
          "updated_at": 1700000000.0
      },
      ...
    }
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProgressStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, file_path: str) -> Optional[dict]:
        """Return stored progress for *file_path*, or None."""
        with self._lock:
            return self._data.get(file_path)

    def save(self, file_path: str, position_ms: int, duration_ms: int) -> None:
        """Record current playback position.  Persists to disk immediately."""
        with self._lock:
            self._data[file_path] = {
                "position_ms": int(position_ms),
                "duration_ms": int(duration_ms),
                "updated_at": time.time(),
            }
            self._write()

    def pct(self, file_path: str) -> float:
        """Return watch fraction 0.0–1.0 for *file_path* (0.0 if unknown)."""
        d = self.get(file_path)
        if not d or not d.get("duration_ms"):
            return 0.0
        return min(d["position_ms"] / d["duration_ms"], 1.0)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info("Loaded progress store (%d entries)", len(self._data))
        except Exception as exc:
            logger.warning("Could not load progress store: %s", exc)
            self._data = {}

    def _write(self) -> None:
        """Write to a temp file then atomically replace — safe on Windows."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            tmp.replace(self._path)
        except Exception as exc:
            logger.warning("Could not write progress store: %s", exc)
