"""
Media organizer — moves downloaded files into the library.

New unified layout
------------------
Movies:
  {MEDIA_DIR}/{Title} [{tmdb_id}]/{Title} ({Year}).ext

TV / Anime:
  {MEDIA_DIR}/{Title} [{tmdb_id}]/S{NN}E{NN} - {Episode Title}.ext
  Season packs keep original filenames.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from server.config import settings

logger = logging.getLogger(__name__)

# Characters not allowed in Windows filenames (excluding colon, handled separately)
_ILLEGAL_CHARS = re.compile(r'[<>"/\\|?*]')
# Collapse multiple spaces
_MULTI_SPACE = re.compile(r"\s{2,}")

# Common video extensions
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"}


def _sanitize(name: str) -> str:
    """Remove characters illegal on Windows/macOS filesystems."""
    if not name:
        return ""
    # Replace colon with " - "
    name = name.replace(":", " - ")
    # Remove other illegal characters
    name = _ILLEGAL_CHARS.sub("", name)
    # Collapse multiple spaces
    name = _MULTI_SPACE.sub(" ", name)
    # Strip leading/trailing dots and spaces
    name = name.strip(" .")
    return name


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
        pass

    def _destination(self, video_path: Path, media) -> Path:
        """Build the destination path for a video file based on media info."""
        ext = video_path.suffix
        media_dir = Path(settings.MEDIA_DIR)
        title = _sanitize(media.title)
        tmdb_id = media.tmdb_id
        folder_name = f"{title} [{tmdb_id}]"

        if media.type == "movie":
            if media.year:
                file_name = f"{title} ({media.year}){ext}"
            else:
                file_name = f"{title}{ext}"
            return media_dir / folder_name / file_name

        # TV / Anime
        season = media.season if media.season is not None else 1

        if media.episode is not None:
            ep_title = ""
            if hasattr(media, "episode_titles") and media.episode_titles:
                ep_title = media.episode_titles.get(media.episode, "")

            if ep_title:
                file_name = f"S{season:02d}E{media.episode:02d} - {_sanitize(ep_title)}{ext}"
            else:
                file_name = f"S{season:02d}E{media.episode:02d}{ext}"
            return media_dir / folder_name / file_name
        else:
            # Season pack — keep original filename
            file_name = video_path.name
            return media_dir / folder_name / file_name

    def organize(self, source: Path, media) -> Path:
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

        # Overwrite if exists
        if dest.exists():
            dest.unlink()

        logger.info("Moving %s → %s", video_file, dest)
        shutil.move(str(video_file), str(dest))

        # Clean up empty staging folders
        try:
            if source.is_dir() and source != video_file.parent:
                shutil.rmtree(source, ignore_errors=True)
        except Exception:
            pass

        return dest
