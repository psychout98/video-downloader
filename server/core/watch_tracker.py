"""
Watch tracker — monitors MPC-BE and archives watched files.

Polls MPC-BE, tracks the maximum playback position reached for each file.
When playback stops after reaching WATCH_THRESHOLD (default 85%),
the file is moved from MEDIA_DIR to ARCHIVE_DIR, preserving relative path.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from server.config import settings
import server.database as db

if TYPE_CHECKING:
    from .progress_store import ProgressStore

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds between MPC-BE polls
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v", ".webm", ".flv"}
SUBTITLE_EXTS = {".srt", ".ass", ".sub", ".ssa", ".nfo", ".idx", ".vtt"}

_PROGRESS_SAVE_INTERVAL = 10  # seconds between progress saves while playing
_TMDB_ID_RE = re.compile(r"\[(\d+)\]")


def _parse_tmdb_id_from_path(path_str: str) -> Optional[int]:
    """Extract TMDB ID from a path like '.../Show [1396]/S01E01.mkv'."""
    if not path_str:
        return None
    m = _TMDB_ID_RE.search(path_str)
    if m:
        return int(m.group(1))
    return None


def _compute_rel_path(file_path: str) -> str:
    """Return the relative path after the [tmdb_id] folder.

    If the file is under MEDIA_DIR or ARCHIVE_DIR, return just the path
    component after the folder containing [tmdb_id].
    Otherwise return just the filename.
    """
    fp = Path(file_path)

    for base in (Path(settings.MEDIA_DIR), Path(settings.ARCHIVE_DIR)):
        try:
            rel = fp.relative_to(base)
            parts = rel.parts
            # parts[0] is the [tmdb_id] folder, rest is the relative path
            if len(parts) > 1:
                return str(Path(*parts[1:]))
        except ValueError:
            continue

    return fp.name


def _remove_if_empty(folder: Path) -> None:
    """Remove folder if it contains no video files anywhere inside it."""
    if not folder.exists() or not folder.is_dir():
        return
    has_video = any(
        f.suffix.lower() in VIDEO_EXTS
        for f in folder.rglob("*")
        if f.is_file()
    )
    if not has_video:
        try:
            shutil.rmtree(str(folder))
            logger.info("Removed empty folder: %s", folder)
        except Exception:
            pass


async def _move_folder_remnants(src_folder: Path, dest_folder: Path) -> None:
    """Move non-video files from src_folder to dest_folder."""
    if not src_folder.exists():
        return
    # If any video files remain, don't touch the folder
    if any(f.suffix.lower() in VIDEO_EXTS for f in src_folder.iterdir() if f.is_file()):
        return
    dest_folder.mkdir(parents=True, exist_ok=True)
    for f in list(src_folder.iterdir()):
        if f.is_file():
            try:
                shutil.move(str(f), str(dest_folder / f.name))
            except Exception:
                pass
    try:
        src_folder.rmdir()
    except Exception:
        pass


class WatchTracker:
    def __init__(self, mpc_client, progress_store: Optional["ProgressStore"] = None):
        self._mpc = mpc_client
        self._progress = progress_store
        self._running = False
        self._prev_file: Optional[str] = None
        self._max_pct: dict[str, float] = {}
        self._stopped_polls: int = 0
        self._last_progress_save: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        asyncio.create_task(self._poll_loop())
        logger.info("WatchTracker started (threshold=%.0f%%)", settings.WATCH_THRESHOLD * 100)

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.debug("WatchTracker tick error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self):
        try:
            status = await self._mpc.get_status()
        except Exception:
            # MPC-BE unreachable — treat as stopped
            if self._prev_file:
                self._stopped_polls += 1
                if self._stopped_polls >= 2:
                    await self._on_stopped(self._prev_file)
            return

        file_path = status.file if hasattr(status, 'file') else ""

        if status.state == 0 or not file_path:
            # Stopped or no file
            self._stopped_polls += 1
            if self._stopped_polls >= 2 and self._prev_file:
                await self._on_stopped(self._prev_file)
            return

        # Playing or paused (state 1 or 2)
        self._stopped_polls = 0

        # File changed — previous file is done
        if self._prev_file and self._prev_file != file_path:
            await self._on_stopped(self._prev_file)

        self._prev_file = file_path

        # Track progress
        if hasattr(status, 'duration_ms') and status.duration_ms > 0:
            pct = status.position_ms / status.duration_ms
            prev = self._max_pct.get(file_path, 0.0)
            self._max_pct[file_path] = max(prev, pct)

            # Save progress periodically
            now = time.monotonic()
            if (now - self._last_progress_save) >= _PROGRESS_SAVE_INTERVAL:
                tmdb_id = _parse_tmdb_id_from_path(file_path)
                if tmdb_id:
                    rel_path = _compute_rel_path(file_path)
                    try:
                        await db.save_watch_progress(
                            tmdb_id=tmdb_id,
                            rel_path=rel_path,
                            position_ms=status.position_ms,
                            duration_ms=status.duration_ms,
                        )
                    except Exception as exc:
                        logger.debug("Could not save progress: %s", exc)
                self._last_progress_save = now

    async def _on_stopped(self, file_path: str):
        """Called when we're confident a file has finished playing."""
        pct = self._max_pct.get(file_path, 0.0)
        logger.debug("Stopped: %s at %.0f%%", file_path, pct * 100)

        if pct >= settings.WATCH_THRESHOLD:
            logger.info("Archiving watched file (%.0f%%): %s", pct * 100, file_path)
            await self._archive(file_path)

        # Clear state
        self._max_pct.pop(file_path, None)
        self._prev_file = None
        self._stopped_polls = 0

    # ------------------------------------------------------------------
    # Archive (move from MEDIA_DIR → ARCHIVE_DIR)
    # ------------------------------------------------------------------

    async def _archive(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            logger.warning("Archive: source not found: %s", file_path)
            return

        media_dir = Path(settings.MEDIA_DIR)
        archive_dir = Path(settings.ARCHIVE_DIR)

        try:
            rel = path.relative_to(media_dir)
        except ValueError:
            logger.debug("Archive: %s is not under MEDIA_DIR", file_path)
            return

        dest = archive_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(path), str(dest))
            logger.info("Moved: %s -> %s", path, dest)
        except Exception as exc:
            logger.error("Archive move failed: %s", exc)
            return

        # Move subtitle/nfo files with the same stem
        for sibling in list(path.parent.glob(path.stem + ".*")):
            if sibling.suffix.lower() in SUBTITLE_EXTS:
                try:
                    shutil.move(str(sibling), str(dest.parent / sibling.name))
                except Exception:
                    pass

        # Move remaining non-video files and clean up
        await _move_folder_remnants(path.parent, dest.parent)
        _remove_if_empty(path.parent)
