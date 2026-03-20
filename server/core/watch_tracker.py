"""
Watch tracker — monitors MPC-BE and archives watched files.

How it works
------------
- Polls MPC-BE every 5 seconds.
- Tracks the maximum playback position reached for each file.
- When playback stops (state=0) after reaching WATCH_THRESHOLD (default 85%),
  the file is moved from the primary NVMe drive to the archive SATA drive,
  preserving its relative path within the media library.

Move rules
----------
Movies:
  After the .mkv is moved, any remaining files in the movie folder
  (poster.jpg, subtitles, etc.) are also moved and the empty folder is removed.

TV / Anime:
  Only the episode file (and any per-episode subtitle files) are moved.
  Season and show folders on the primary drive are removed once they contain
  no more video files.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..config import settings
from ..clients.mpc_client import MPCClient

if TYPE_CHECKING:
    from .progress_store import ProgressStore

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds between MPC-BE polls
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".m4v"}
SUBTITLE_EXTS = {".srt", ".ass", ".sub", ".idx", ".vtt", ".nfo"}


_PROGRESS_SAVE_INTERVAL = 10  # seconds between progress saves while playing


class WatchTracker:
    def __init__(self, mpc: MPCClient, progress_store: Optional["ProgressStore"] = None):
        self._mpc = mpc
        self._progress = progress_store
        self._running = False

        # (primary_dir, archive_dir) pairs — order matters for path matching
        self._dir_pairs: list[tuple[Path, Path]] = [
            (Path(settings.MOVIES_DIR),  Path(settings.MOVIES_DIR_ARCHIVE)),
            (Path(settings.TV_DIR),      Path(settings.TV_DIR_ARCHIVE)),
            (Path(settings.ANIME_DIR),   Path(settings.ANIME_DIR_ARCHIVE)),
        ]

        self._prev_file: Optional[str] = None
        self._max_pct: dict[str, float] = {}   # file_path -> highest fraction watched
        self._stopped_polls: int = 0            # consecutive state=0 polls
        self._last_progress_save: float = 0.0  # timestamp of last progress write

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

        if status.state in (1, 2) and status.file:
            # Playing or paused — record progress
            self._stopped_polls = 0
            if status.duration_ms > 0:
                pct = status.position_ms / status.duration_ms
                prev = self._max_pct.get(status.file, 0.0)
                self._max_pct[status.file] = max(prev, pct)

                # Persist position periodically so the user can resume after restart
                now = time.monotonic()
                if self._progress and (now - self._last_progress_save) >= _PROGRESS_SAVE_INTERVAL:
                    self._progress.save(status.file, status.position_ms, status.duration_ms)
                    self._last_progress_save = now

            # File changed while something was playing → previous file done
            if self._prev_file and self._prev_file != status.file:
                await self._on_stopped(self._prev_file)

            self._prev_file = status.file

        elif status.state == 0:
            # Stopped
            self._stopped_polls += 1
            # Wait for 2 consecutive stopped polls (~10s) to avoid transient glitches
            if self._stopped_polls >= 2 and self._prev_file:
                await self._on_stopped(self._prev_file)
        else:
            self._stopped_polls = 0

    async def _on_stopped(self, file_path: str):
        """Called when we're confident a file has finished playing."""
        pct = self._max_pct.get(file_path, 0.0)
        logger.debug("Stopped: %s at %.0f%%", file_path, pct * 100)

        # Final progress save on stop (so resume position is accurate)
        if self._progress:
            existing = self._progress.get(file_path)
            if existing and existing.get("duration_ms"):
                pos = int(existing["duration_ms"] * pct)
                self._progress.save(file_path, pos, existing["duration_ms"])

        if pct >= settings.WATCH_THRESHOLD:
            logger.info("Archiving watched file (%.0f%%): %s", pct * 100, file_path)
            await self._archive(file_path)

        self._max_pct.pop(file_path, None)
        self._prev_file = None
        self._stopped_polls = 0

    # ------------------------------------------------------------------
    # Archive (move from primary → archive drive)
    # ------------------------------------------------------------------

    async def _archive(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            logger.warning("Archive: source not found: %s", file_path)
            return

        for primary_dir, archive_dir in self._dir_pairs:
            try:
                rel = path.relative_to(primary_dir)
            except ValueError:
                continue

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

            is_movie = (primary_dir == Path(settings.MOVIES_DIR))

            if is_movie:
                # Move any remaining non-video files (poster, etc.) and remove folder
                await _move_folder_remnants(path.parent, dest.parent)
            else:
                # TV/anime: remove empty season and show folders
                _remove_if_empty(path.parent)
                _remove_if_empty(path.parent.parent)

            return

        logger.debug("Archive: %s is not under any primary media dir", file_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _move_folder_remnants(src_folder: Path, dest_folder: Path) -> None:
    """Move non-video files from src_folder to dest_folder, then remove src if empty."""
    if not src_folder.exists():
        return
    # If any video files remain, don't touch the folder
    if any(f.suffix.lower() in VIDEO_EXTS for f in src_folder.iterdir() if f.is_file()):
        return
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
