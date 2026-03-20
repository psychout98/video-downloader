"""
Media library scanner.

Walks both the primary (NVMe) and archive (SATA) media directories and returns
structured metadata suitable for the Netflix-style card grid.

Each item has a 'storage' field:
  "new"     - only on primary (NVMe) drive
  "archive" - only on archive (SATA) drive
  "mixed"   - TV/anime show with episodes on both drives

TV shows that share a title across both drives are merged into a single card
with combined episode/size counts.

Title overrides
---------------
``data/title_overrides.json`` maps the display title (as the scanner parses it
from the filename) to a corrected TMDB lookup title/year.  Example entry::

    "Thor Love and Thunder": { "title": "Thor: Love and Thunder", "year": 2022 }

A plain string value is also accepted::

    "Dont Look Up": "Don't Look Up"

When an override is found the item gains ``tmdb_title`` / ``tmdb_year`` fields
which the frontend uses instead of ``title`` / ``year`` for poster lookups.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv", ".m4v"}
POSTER_NAMES = {"poster.jpg", "poster.png", "movie.jpg", "movie.png",
                "folder.jpg", "folder.png", "thumb.jpg", "cover.jpg"}

# --- Filename parsers -------------------------------------------------

_PAREN_YEAR = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")
_DOT_YEAR   = re.compile(r"^(.+?)[\.\s_](\d{4})(?:[\.\s_]|$)")
_DASH_YEAR  = re.compile(r"^(.+?)\s+-\s+(\d{4})\s*$")
_QUALITY    = re.compile(
    r"\b(2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|web-dl|webrip|remux|hevc|x265|x264|hdr|dv|atmos)\b",
    re.I,
)


def _clean_title(raw: str) -> str:
    if "." in raw and " " not in raw:
        raw = raw.replace(".", " ")
    raw = raw.replace("_", " ")
    raw = _QUALITY.sub("", raw)
    raw = re.sub(r"\[.*?\]|\(.*?\)", "", raw)
    return re.sub(r"\s{2,}", " ", raw).strip(" .-")


def _extract_title_year(name: str) -> tuple[str, Optional[int]]:
    for pattern in (_PAREN_YEAR, _DASH_YEAR):
        m = pattern.match(name)
        if m:
            return _clean_title(m.group(1)), int(m.group(2))
    m = _DOT_YEAR.match(name)
    if m:
        return _clean_title(m.group(1)), int(m.group(2))
    return _clean_title(name), None


def _safe_poster_key(s: str) -> str:
    """Strip characters that are illegal in Windows filenames."""
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


def _find_poster(directory: Path, title_key: Optional[str] = None) -> Optional[str]:
    """Return the path to a poster image for the given media directory.

    Checks the central posters folder first using, in order:
      1. ``title_key`` — explicit "Title (Year)" string, used for flat files
         where directory.name would just be "Movies" (same for every title).
      2. ``directory.name`` — works for content already in a per-title subfolder.
    Falls back to legacy posters still living inside the media folder.
    """
    from ..config import settings  # local import to avoid circular at module load

    posters_dir = Path(settings.POSTERS_DIR)

    def _check(key: str) -> Optional[str]:
        safe = _safe_poster_key(key)
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            p = posters_dir / f"{safe}{ext}"
            if p.exists():
                return str(p)
        return None

    # 1. Title-based key (most reliable, especially for flat files)
    if title_key:
        hit = _check(title_key)
        if hit:
            return hit

    # 2. Directory-name key (works for per-title subfolders)
    if directory.name != title_key:
        hit = _check(directory.name)
        if hit:
            return hit

    # 3. Legacy: poster stored inside the media folder
    for name in POSTER_NAMES:
        p = directory / name
        if p.exists():
            return str(p)

    return None


def _largest_video(directory: Path) -> Optional[Path]:
    candidates = [
        p for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


# --- Directory scanner ------------------------------------------------

def scan_directory(base_dir: Path, media_type: str, storage: str) -> list[dict]:
    """
    Scan *base_dir* and return a list of media item dicts.
    *storage* is "new" or "archive" and is attached to every result.
    """
    results: list[dict] = []
    if not base_dir.exists():
        logger.debug("Library dir does not exist: %s", base_dir)
        return results

    for entry in sorted(base_dir.iterdir(), key=lambda p: p.name):
        try:
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                title, year = _extract_title_year(entry.name)
                video_files = [
                    p for p in entry.rglob("*")
                    if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
                ]
                if not video_files:
                    continue
                video_files.sort(key=lambda p: (p.parent.name, p.name))
                total_size = sum(p.stat().st_size for p in video_files)
                first_video = video_files[0]
                title_key = f"{title} ({year})" if year else title
                poster = (
                    _find_poster(entry, title_key=title_key)
                    or _find_poster(first_video.parent, title_key=title_key)
                )
                results.append({
                    "title": title,
                    "year": year,
                    "type": media_type,
                    "path": str(first_video),
                    "folder": str(entry),
                    "file_count": len(video_files),
                    "size_bytes": total_size,
                    "poster": poster,
                    "modified_at": int(entry.stat().st_mtime),
                    "storage": storage,
                })

            elif entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS:
                title, year = _extract_title_year(entry.stem)
                # For flat files entry.parent is the base dir (e.g. "Movies"),
                # not a per-title folder — pass an explicit key so the right
                # poster is found instead of a shared "Movies.jpg".
                title_key = f"{title} ({year})" if year else title
                poster = _find_poster(entry.parent, title_key=title_key)
                results.append({
                    "title": title,
                    "year": year,
                    "type": media_type,
                    "path": str(entry),
                    "folder": str(entry.parent),
                    "file_count": 1,
                    "size_bytes": entry.stat().st_size,
                    "poster": poster,
                    "modified_at": int(entry.stat().st_mtime),
                    "storage": storage,
                })

        except Exception as exc:
            logger.warning("Error scanning %s: %s", entry, exc)

    return results


def _merge_entries(primary: list[dict], archive: list[dict], media_type: str) -> list[dict]:
    """
    Merge primary and archive entries for the same media type.
    TV/anime shows with the same title on both drives are combined into one card.
    Movies (shouldn't be on both, but handle gracefully) are kept separate.
    """
    if media_type == "movie":
        # Movies: just concatenate — shouldn't be on both drives simultaneously
        return primary + archive

    # TV / anime: merge by lower-cased title
    by_title: dict[str, dict] = {}

    for item in primary:
        key = item["title"].lower()
        by_title[key] = item.copy()

    for item in archive:
        key = item["title"].lower()
        if key in by_title:
            existing = by_title[key]
            existing["file_count"] += item["file_count"]
            existing["size_bytes"] += item["size_bytes"]
            existing["storage"] = "mixed"
            # Keep the most recent modification time
            existing["modified_at"] = max(existing["modified_at"], item["modified_at"])
            # Use primary poster if available, fall back to archive
            if not existing.get("poster") and item.get("poster"):
                existing["poster"] = item["poster"]
            # Store both folder paths so the UI can reference them
            existing["folder_archive"] = item["folder"]
        else:
            by_title[key] = item.copy()

    return list(by_title.values())


# --- Title overrides --------------------------------------------------

_OVERRIDES_FILE = Path(__file__).parent.parent.parent / "data" / "title_overrides.json"


def _load_overrides() -> dict:
    """Load data/title_overrides.json, ignoring keys that start with '_'."""
    if not _OVERRIDES_FILE.exists():
        return {}
    try:
        raw = json.loads(_OVERRIDES_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception as exc:
        logger.warning("Could not load title_overrides.json: %s", exc)
        return {}


def _apply_override(item: dict, overrides: dict) -> None:
    """Stamp tmdb_title / tmdb_year onto *item* if a matching override exists."""
    entry = overrides.get(item["title"])
    if entry is None:
        return
    if isinstance(entry, str):
        item["tmdb_title"] = entry
    elif isinstance(entry, dict):
        if "title" in entry:
            item["tmdb_title"] = entry["title"]
        if "year" in entry:
            item["tmdb_year"] = entry["year"]


# --- Public API -------------------------------------------------------

class LibraryScanner:
    """
    Scans primary (NVMe) and archive (SATA) media directories.
    Caches the result for *cache_ttl* seconds.
    """

    def __init__(
        self,
        movies_dir: str,   tv_dir: str,   anime_dir: str,
        movies_archive: str, tv_archive: str, anime_archive: str,
        cache_ttl: int = 60,
    ):
        self._dirs = [
            (Path(movies_dir),   Path(movies_archive),   "movie"),
            (Path(tv_dir),       Path(tv_archive),       "tv"),
            (Path(anime_dir),    Path(anime_archive),    "anime"),
        ]
        self._ttl = cache_ttl
        self._cache: list[dict] = []
        self._cache_time: float = 0.0

    def scan(self, force: bool = False) -> list[dict]:
        if not force and (time.time() - self._cache_time) < self._ttl:
            return self._cache

        overrides = _load_overrides()

        results: list[dict] = []
        for primary_dir, archive_dir, media_type in self._dirs:
            primary_items = scan_directory(primary_dir, media_type, "new")
            archive_items = scan_directory(archive_dir, media_type, "archive")
            merged = _merge_entries(primary_items, archive_items, media_type)
            results.extend(merged)

        # Stamp tmdb_title / tmdb_year where an override exists
        for item in results:
            _apply_override(item, overrides)

        results.sort(key=lambda x: x.get("modified_at", 0), reverse=True)

        self._cache = results
        self._cache_time = time.time()
        loaded = len(overrides)
        logger.info(
            "Library scan: %d items (%d title override%s active)",
            len(results), loaded, "s" if loaded != 1 else "",
        )
        return results
