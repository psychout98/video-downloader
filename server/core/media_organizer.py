"""
Media organizer — moves downloaded files into the library in Plex-compatible paths.

Naming conventions
------------------
Movies:
  {MEDIA_DIR}/{Title} ({Year})/{Title} ({Year}).ext
  e.g. C:/Users/Me/Media/Inception (2010)/Inception (2010).mkv

TV Shows / Anime:
  {MEDIA_DIR}/{Series Name}/Season {N}/{Series Name} - S{NN}E{NN} - {Episode Title}.ext
  e.g. C:/Users/Me/Media/Breaking Bad/Season 1/Breaking Bad - S01E01 - Pilot.mkv

Quality tags (optional, placed before extension for visual identification):
  Inception (2010) [2160p DV Atmos].mkv
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from ..config import settings
from ..clients.tmdb_client import MediaInfo

logger = logging.getLogger(__name__)

# Characters not allowed in Windows filenames
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Collapse multiple spaces
_MULTI_SPACE = re.compile(r"\s{2,}")

# Common video extensions we'll look for after extracting from an archive or
# when a download folder contains multiple files
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv"}


def _sanitize(name: str) -> str:
    """Remove characters illegal on Windows/macOS filesystems."""
    name = _ILLEGAL_CHARS.sub("", name)
    return _MULTI_SPACE.sub(" ", name).strip(" .")


def _pick_video_file(directory: Path) -> Optional[Path]:
    """Return the largest video file in *directory* (recursive)."""
    best: Optional[Path] = None
    best_size = 0
    for p in directory.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            size = p.stat().st_size
            if size > best_size:
                best_size = size
                best = p
    return best


class MediaOrganizer:
    def __init__(self):
        self._media_dir = Path(settings.MEDIA_DIR)

    def _base_dir(self, media: MediaInfo) -> Path:
        return self._media_dir

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def organize(self, source: Path, media: MediaInfo) -> Path:
        """
        Move *source* (a file or directory) to the appropriate library location.
        Returns the final file path.
        """
        # Resolve the actual video file if source is a directory
        if source.is_dir():
            video_file = _pick_video_file(source)
            if not video_file:
                raise FileNotFoundError(f"No video file found in {source}")
        else:
            video_file = source

        dest = self._destination(video_file, media)
        dest.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Moving %s → %s", video_file, dest)
        shutil.move(str(video_file), str(dest))

        # Clean up empty staging folders
        try:
            if source.is_dir() and source != video_file.parent:
                shutil.rmtree(source, ignore_errors=True)
        except Exception:
            pass

        return dest

    def _destination(self, video_file: Path, media: MediaInfo) -> Path:
        ext = video_file.suffix.lower() or ".mkv"
        base = self._base_dir(media)

        if media.type == "movie":
            folder_name = _sanitize(
                f"{media.title} ({media.year})" if media.year else media.title
            )
            file_name = _sanitize(
                f"{media.title} ({media.year}){ext}"
                if media.year
                else f"{media.title}{ext}"
            )
            return base / folder_name / file_name

        # TV / Anime
        show_dir = _sanitize(media.title)
        season_num = media.season or 1
        season_dir = f"Season {season_num:02d}"

        if media.episode is not None:
            ep_title = media.episode_titles.get(media.episode, "")
            ep_suffix = (
                f" - {_sanitize(ep_title)}" if ep_title else ""
            )
            file_name = _sanitize(
                f"{media.title} - S{season_num:02d}E{media.episode:02d}"
                f"{ep_suffix}{ext}"
            )
        else:
            # Season pack — keep original filename but place in correct folder
            file_name = _sanitize(video_file.stem + ext)

        return base / show_dir / season_dir / file_name
