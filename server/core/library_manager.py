"""
Unified library manager — scan + normalize folders + smart poster refresh.

Supports both the new unified layout (MEDIA_DIR/ARCHIVE_DIR) and
legacy type-based directories (MOVIES_DIR, TV_DIR, ANIME_DIR).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from server.config import settings

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv", ".m4v", ".webm"}

# --- Filename parsers -------------------------------------------------

_PAREN_YEAR = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")
_DOT_YEAR   = re.compile(r"^(.+?)[\.\s_](\d{4})(?:[\.\s_]|$)")
_DASH_YEAR  = re.compile(r"^(.+?)\s+-\s+(\d{4})\s*$")
_QUALITY    = re.compile(
    r"\b(2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|web-dl|webrip|remux|hevc|x265|x264|hdr|dv|atmos)\b",
    re.I,
)
_TMDB_ID_RE = re.compile(r"^(.+?)\s*\[(\d+)\]$")


def _clean_title(raw: str) -> str:
    """Clean up a raw folder/file name into a human-readable title."""
    # Replace dots with spaces if the string looks like a dot-separated name
    if "." in raw and " " not in raw:
        raw = raw.replace(".", " ")
    raw = raw.replace("_", " ")
    raw = _QUALITY.sub("", raw)
    raw = re.sub(r"\[.*?\]|\(.*?\)", "", raw)
    return re.sub(r"\s{2,}", " ", raw).strip(" .-")


def _extract_title_year(name: str) -> tuple[str, Optional[int]]:
    """Extract title and year from a folder name."""
    for pattern in (_PAREN_YEAR, _DASH_YEAR):
        m = pattern.match(name)
        if m:
            return _clean_title(m.group(1)), int(m.group(2))
    m = _DOT_YEAR.match(name)
    if m:
        return _clean_title(m.group(1)), int(m.group(2))
    return _clean_title(name), None


def _safe_folder(name: str) -> str:
    """Make a title safe for use as a Windows/macOS folder name."""
    name = re.sub(r":\s*", " - ", name)
    name = re.sub(r'[\\/*?"<>|]', "", name)
    return name.strip(" .")


def _find_poster(posters_dir: Path, tmdb_id: int) -> Optional[str]:
    """Return the path to a cached poster for the given tmdb_id."""
    for ext in (".jpg", ".png", ".jpeg", ".webp"):
        p = posters_dir / f"{tmdb_id}{ext}"
        if p.exists():
            return str(p)
    return None


# --- Directory scanner ------------------------------------------------

def _scan_directory(base_dir: Path, posters_dir: Path, storage: str) -> list[dict]:
    """Scan *base_dir* and return a list of media item dicts."""
    results: list[dict] = []
    if not base_dir.exists():
        return results

    for entry in sorted(base_dir.iterdir(), key=lambda p: p.name):
        try:
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                # Check for tmdb_id in folder name
                tmdb_match = _TMDB_ID_RE.match(entry.name)
                if tmdb_match:
                    tmdb_id = int(tmdb_match.group(2))
                    title = tmdb_match.group(1).strip()
                    year = None
                    # Try to extract year from the title part
                    paren_m = _PAREN_YEAR.match(title)
                    if paren_m:
                        title = paren_m.group(1).strip()
                        year = int(paren_m.group(2))
                else:
                    tmdb_id = None
                    title, year = _extract_title_year(entry.name)

                video_files = [
                    p for p in entry.rglob("*")
                    if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
                ]
                if not video_files:
                    continue

                total_size = sum(p.stat().st_size for p in video_files)
                poster = _find_poster(posters_dir, tmdb_id) if tmdb_id else None

                results.append({
                    "title": title,
                    "year": year,
                    "tmdb_id": tmdb_id,
                    "type": "movie",  # will be overridden by context
                    "path": str(video_files[0]),
                    "folder": str(entry),
                    "folder_name": entry.name,
                    "file_count": len(video_files),
                    "size_bytes": total_size,
                    "poster": poster,
                    "modified_at": int(entry.stat().st_mtime),
                    "storage": storage,
                })

        except Exception as exc:
            logger.warning("Error scanning %s: %s", entry, exc)

    return results


def _merge_entries(media: list[dict], archive: list[dict]) -> list[dict]:
    """Merge media and archive entries, combining those with the same tmdb_id or folder_name."""
    by_key: dict = {}

    def _get_key(item):
        if item.get("tmdb_id"):
            return ("tmdb", item["tmdb_id"])
        return ("folder", item.get("folder_name", ""))

    for item in media:
        key = _get_key(item)
        entry = item.copy()
        entry["location"] = "media"
        by_key[key] = entry

    for item in archive:
        key = _get_key(item)
        if key in by_key:
            existing = by_key[key]
            existing["file_count"] += item["file_count"]
            existing["size_bytes"] += item["size_bytes"]
            existing["modified_at"] = max(existing["modified_at"], item["modified_at"])
            existing["location"] = "both"
            if not existing.get("poster") and item.get("poster"):
                existing["poster"] = item["poster"]
        else:
            entry = item.copy()
            entry["location"] = "archive"
            by_key[key] = entry

    return list(by_key.values())


# --- Library Manager --------------------------------------------------

class LibraryManager:
    """Unified library scan + normalize + smart poster refresh."""

    def __init__(self, cache_ttl: int = 60):
        self._ttl = cache_ttl
        self._cache: Optional[list[dict]] = None
        self._cache_time: float = 0.0

    def scan(self, force: bool = False) -> list[dict]:
        """Scan all library directories and return media items."""
        if not force and self._cache is not None and (time.time() - self._cache_time) < self._ttl:
            return self._cache

        results: list[dict] = []
        posters_dir = Path(settings.POSTERS_DIR)

        # Scan new unified dirs
        media_dir = Path(settings.MEDIA_DIR) if hasattr(settings, 'MEDIA_DIR') else None
        archive_dir = Path(settings.ARCHIVE_DIR) if hasattr(settings, 'ARCHIVE_DIR') else None

        if media_dir:
            results.extend(_scan_directory(media_dir, posters_dir, "media"))
        if archive_dir:
            results.extend(_scan_directory(archive_dir, posters_dir, "archive"))

        # Also scan legacy dirs
        legacy_pairs = [
            ("MOVIES_DIR", "MOVIES_DIR_ARCHIVE", "movie"),
            ("TV_DIR", "TV_DIR_ARCHIVE", "tv"),
            ("ANIME_DIR", "ANIME_DIR_ARCHIVE", "anime"),
        ]

        for primary_attr, archive_attr, media_type in legacy_pairs:
            primary = Path(getattr(settings, primary_attr, ""))
            archive = Path(getattr(settings, archive_attr, ""))

            # Skip if same as unified dirs
            if media_dir and primary == media_dir:
                continue
            if archive_dir and archive == archive_dir:
                continue

            primary_items = _scan_directory(primary, posters_dir, "media")
            archive_items = _scan_directory(archive, posters_dir, "archive")

            for item in primary_items + archive_items:
                item["type"] = media_type
            results.extend(primary_items)
            results.extend(archive_items)

        results.sort(key=lambda x: x.get("modified_at", 0), reverse=True)
        self._cache = results
        self._cache_time = time.time()

        logger.info("Library scan: %d items", len(results))
        return results

    async def refresh(self, tmdb_client) -> dict:
        """Refresh library: resolve TMDB IDs, upsert media items, fetch posters."""
        import server.database as db

        posters_dir = Path(settings.POSTERS_DIR)
        posters_dir.mkdir(parents=True, exist_ok=True)

        added = 0
        errors: list[str] = []

        # Scan current state
        media_dir = Path(settings.MEDIA_DIR)
        archive_dir = Path(settings.ARCHIVE_DIR)

        all_entries = []
        all_entries.extend(_scan_directory(media_dir, posters_dir, "media"))
        all_entries.extend(_scan_directory(archive_dir, posters_dir, "archive"))

        for entry in all_entries:
            tmdb_id = entry.get("tmdb_id")
            title = entry.get("title", "")
            year = entry.get("year")
            folder_name = entry.get("folder_name", "")

            if not tmdb_id:
                errors.append(f"No TMDB ID for folder: {folder_name}")
                continue

            try:
                # Upsert to database
                await db.upsert_media_item(
                    tmdb_id=tmdb_id,
                    title=title,
                    year=year,
                    media_type="movie",
                    folder_name=folder_name,
                )
                added += 1

                # Check/download poster
                existing_poster = _find_poster(posters_dir, tmdb_id)
                if not existing_poster:
                    try:
                        resolved_title, resolved_year, poster_path = await tmdb_client.fuzzy_resolve(
                            title, year=year,
                        )
                        if poster_path:
                            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                                r = await client.get(poster_url)
                                r.raise_for_status()
                                dest = posters_dir / f"{tmdb_id}.jpg"
                                dest.write_bytes(r.content)
                    except Exception as exc:
                        logger.warning("Could not fetch poster for %s: %s", title, exc)

            except Exception as exc:
                errors.append(f"Error processing {folder_name}: {exc}")

        # Invalidate cache
        self._cache = None
        self._cache_time = 0.0

        summary = {
            "added": added,
            "errors": errors,
            "total_items": len(all_entries),
        }
        logger.info("Library refresh: added=%d, errors=%d", added, len(errors))
        return summary
