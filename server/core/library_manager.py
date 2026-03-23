"""
Unified library manager — scan + normalize folders + smart poster refresh.

Replaces the separate "normalize folders" and "refresh posters" buttons
with a single refresh operation.

Refresh pipeline
----------------
1. Scan all media directories (primary + archive)
2. For each item, resolve canonical title via TMDB (rate limited)
3. If current folder name ≠ canonical name, rename the folder
4. If poster is missing OR item was just renamed, fetch poster from TMDB
5. Save updated library metadata to data/library.json
6. Return a summary of changes

Data files managed
------------------
- data/posters/         — cached poster images keyed by "Title (Year)"
- data/playback.json    — watch progress per file (managed by ProgressStore)
- data/library.json     — cached library scan metadata
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

from ..config import settings

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


def _safe_folder(name: str) -> str:
    """Make a title safe for use as a Windows/macOS folder name."""
    name = re.sub(r":\s*", " - ", name)
    name = re.sub(r'[\\/*?"<>|]', "", name)
    return name.strip(" .")


def _find_poster(posters_dir: Path, title_key: str) -> Optional[str]:
    """Return the path to a cached poster for the given title key."""
    safe = _safe_poster_key(title_key)
    for ext in (".jpg", ".png", ".jpeg", ".webp"):
        p = posters_dir / f"{safe}{ext}"
        if p.exists():
            return str(p)
    return None


# --- Directory scanner ------------------------------------------------

def _scan_directory(base_dir: Path, media_type: str, storage: str) -> list[dict]:
    """Scan *base_dir* and return a list of media item dicts."""
    results: list[dict] = []
    if not base_dir.exists():
        return results

    posters_dir = Path(settings.POSTERS_DIR)

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
                title_key = f"{title} ({year})" if year else title
                poster = _find_poster(posters_dir, title_key)
                results.append({
                    "title": title,
                    "year": year,
                    "type": media_type,
                    "path": str(video_files[0]),
                    "folder": str(entry),
                    "file_count": len(video_files),
                    "size_bytes": total_size,
                    "poster": poster,
                    "modified_at": int(entry.stat().st_mtime),
                    "storage": storage,
                })

            elif entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS:
                title, year = _extract_title_year(entry.stem)
                title_key = f"{title} ({year})" if year else title
                poster = _find_poster(posters_dir, title_key)
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
    """Merge primary and archive entries for the same media type."""
    if media_type == "movie":
        return primary + archive

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
            existing["modified_at"] = max(existing["modified_at"], item["modified_at"])
            if not existing.get("poster") and item.get("poster"):
                existing["poster"] = item["poster"]
            existing["folder_archive"] = item["folder"]
        else:
            by_title[key] = item.copy()

    return list(by_title.values())


# --- Library Manager --------------------------------------------------

class LibraryManager:
    """Unified library scan + normalize + smart poster refresh."""

    def __init__(self, cache_ttl: int = 60):
        self._dirs = [
            (Path(settings.MEDIA_DIR), Path(settings.ARCHIVE_DIR), "media"),
        ]
        self._ttl = cache_ttl
        self._cache: list[dict] = []
        self._cache_time: float = 0.0
        self._data_dir = Path(settings.POSTERS_DIR).parent  # data/
        self._library_json = self._data_dir / "library.json"

    def scan(self, force: bool = False) -> list[dict]:
        """Scan all library directories and return media items."""
        if not force and (time.time() - self._cache_time) < self._ttl:
            return self._cache

        results: list[dict] = []
        for primary_dir, archive_dir, media_type in self._dirs:
            primary_items = _scan_directory(primary_dir, media_type, "new")
            archive_items = _scan_directory(archive_dir, media_type, "archive")
            merged = _merge_entries(primary_items, archive_items, media_type)
            results.extend(merged)

        results.sort(key=lambda x: x.get("modified_at", 0), reverse=True)
        self._cache = results
        self._cache_time = time.time()

        # Persist to library.json
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._library_json.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            tmp.replace(self._library_json)
        except Exception as exc:
            logger.warning("Could not write library.json: %s", exc)

        logger.info("Library scan: %d items", len(results))
        return results

    async def refresh(self, tmdb_client) -> dict:
        """Unified refresh: normalize folders + smart poster refresh.

        1. For each folder in every library dir, resolve the canonical TMDB title.
        2. If the current folder name differs, rename it.
        3. If the poster is missing OR the folder was renamed, fetch the poster.
        4. Rescan the library to pick up all changes.

        Returns a summary dict with counts.
        """
        posters_dir = Path(settings.POSTERS_DIR)
        posters_dir.mkdir(parents=True, exist_ok=True)

        renamed_count = 0
        posters_fetched = 0
        errors: list[str] = []

        for primary_dir, archive_dir, media_type in self._dirs:
            for lib_dir in (primary_dir, archive_dir):
                if not lib_dir.exists():
                    continue

                for entry in sorted(lib_dir.iterdir()):
                    if not entry.is_dir() or entry.name.startswith("."):
                        continue

                    # Check for video files
                    has_video = any(
                        f.suffix.lower() in VIDEO_EXTENSIONS
                        for f in entry.rglob("*") if f.is_file()
                    )
                    if not has_video:
                        continue

                    current_name = entry.name
                    parsed_title, parsed_year = _extract_title_year(current_name)

                    # Rate limit TMDB requests
                    await asyncio.sleep(0.25)

                    # Resolve canonical title
                    try:
                        canonical_title, canonical_year, poster_path = await tmdb_client.fuzzy_resolve(
                            parsed_title, media_type=media_type, year=parsed_year,
                        )
                    except Exception as exc:
                        errors.append(f"{current_name}: TMDB miss — {exc}")
                        continue

                    if not canonical_year:
                        canonical_year = parsed_year

                    new_name = _safe_folder(
                        f"{canonical_title} ({canonical_year})" if canonical_year
                        else canonical_title
                    )

                    was_renamed = False

                    # Rename if needed
                    if new_name != current_name:
                        new_path = entry.parent / new_name
                        if new_path.exists():
                            errors.append(
                                f"Skip rename '{current_name}' → '{new_name}': destination exists"
                            )
                        else:
                            try:
                                entry.rename(new_path)
                                renamed_count += 1
                                was_renamed = True
                                logger.info("Renamed: '%s' → '%s'", current_name, new_name)
                                entry = new_path  # update reference
                            except Exception as exc:
                                errors.append(f"Rename failed '{current_name}': {exc}")

                    # Smart poster refresh: fetch if missing OR renamed
                    poster_key = new_name if was_renamed else current_name
                    title_key_for_poster = _safe_poster_key(poster_key)
                    existing_poster = _find_poster(posters_dir, poster_key)

                    if (not existing_poster or was_renamed) and poster_path:
                        try:
                            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                                r = await client.get(poster_url)
                                r.raise_for_status()
                                dest = posters_dir / f"{title_key_for_poster}.jpg"
                                dest.write_bytes(r.content)
                                posters_fetched += 1
                        except Exception as exc:
                            errors.append(f"Poster download failed for '{poster_key}': {exc}")

        # Rescan library to pick up changes
        self.scan(force=True)

        summary = {
            "renamed": renamed_count,
            "posters_fetched": posters_fetched,
            "errors": errors,
            "total_items": len(self._cache),
        }
        logger.info(
            "Library refresh: renamed=%d, posters=%d, errors=%d",
            renamed_count, posters_fetched, len(errors),
        )
        return summary
