"""
One-time migration from legacy layout to new unified layout.

Migration steps:
1. Config: 6 directory settings → MEDIA_DIR + ARCHIVE_DIR
2. Library data: library.json → media_items table (with TMDB ID lookup)
3. Watch progress: playback.json → watch_progress table
4. Poster cache: rename "Title (Year).jpg" → "{tmdb_id}.jpg"
5. Filesystem: move files from type-based dirs into flat MEDIA_DIR/{Title} [{tmdb_id}]/

The migration is idempotent — it checks MIGRATED=True in .env and skips if already done.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from ..config import settings, _ENV_FILE
from ..database import DB_PATH, upsert_media_item, save_watch_progress

import aiosqlite

logger = logging.getLogger(__name__)


def _legacy_userprofile(subdir: str) -> str:
    """Old default media dir: %USERPROFILE%\\Media\\<subdir>."""
    return str(Path(os.path.expandvars("%USERPROFILE%")) / "Media" / subdir)


# Old per-type directory defaults (for migrating existing installs)
_OLD_MOVIES_DIR = _legacy_userprofile("Movies")
_OLD_TV_DIR = _legacy_userprofile("TV Shows")
_OLD_ANIME_DIR = _legacy_userprofile("Anime")
_OLD_MOVIES_DIR_ARCHIVE = "D:\\Media\\Movies"
_OLD_TV_DIR_ARCHIVE = "D:\\Media\\TV Shows"
_OLD_ANIME_DIR_ARCHIVE = "D:\\Media\\Anime"

# Regex to parse "Title (Year)" from folder names
_PAREN_YEAR = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")
# Regex to parse "Title [tmdb_id]" from new-style folder names
_TMDB_ID_RE = re.compile(r"^(.+?)\s*\[(\d+)\]$")
# Episode pattern
_EPISODE_RE = re.compile(r"S(\d{2})E(\d{2})", re.I)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".mov", ".wmv", ".flv", ".m4v"}


def _safe_folder(name: str) -> str:
    """Make a title safe for use as a folder name."""
    name = re.sub(r":\s*", " - ", name)
    name = re.sub(r'[\\/*?"<>|]', "", name)
    return name.strip(" .")


def _safe_poster_key(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


async def check_migration_needed() -> bool:
    """Return True if migration has NOT been done yet."""
    return not settings.MIGRATED


async def run_migration(tmdb_client=None) -> dict:
    """Run the full migration pipeline.

    Args:
        tmdb_client: TMDBClient instance for resolving TMDB IDs.
                     If None, TMDB lookups are skipped and migration is limited.

    Returns:
        Summary dict with counts of migrated items.
    """
    summary = {
        "config_migrated": False,
        "library_items_migrated": 0,
        "progress_entries_migrated": 0,
        "posters_renamed": 0,
        "files_moved": 0,
        "errors": [],
    }

    try:
        # Step 1: Migrate library data (library.json → media_items table)
        await _migrate_library_data(tmdb_client, summary)

        # Step 2: Migrate watch progress (playback.json → watch_progress table)
        await _migrate_watch_progress(summary)

        # Step 3: Migrate poster cache (rename files)
        await _migrate_posters(summary)

        # Step 4: Move files into new directory structure
        await _migrate_filesystem(summary)

        # Step 5: Update .env config
        _migrate_config(summary)

        # Mark migration as complete
        _set_env_key("MIGRATED", "True")
        summary["config_migrated"] = True

    except Exception as exc:
        summary["errors"].append(f"Migration failed: {exc}")
        logger.error("Migration failed: %s", exc, exc_info=True)

    logger.info(
        "Migration complete: library=%d, progress=%d, posters=%d, files=%d, errors=%d",
        summary["library_items_migrated"],
        summary["progress_entries_migrated"],
        summary["posters_renamed"],
        summary["files_moved"],
        len(summary["errors"]),
    )
    return summary


# ── Step 1: Library data migration ───────────────────────────────────────────

async def _migrate_library_data(tmdb_client, summary: dict) -> None:
    """Read library.json and insert entries into media_items table."""
    data_dir = Path(settings.POSTERS_DIR).parent
    library_json = data_dir / "library.json"

    if not library_json.exists():
        logger.info("No library.json found — scanning directories instead")
        await _scan_and_register(tmdb_client, summary)
        return

    try:
        with open(library_json, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as exc:
        summary["errors"].append(f"Could not read library.json: {exc}")
        return

    for item in items:
        try:
            title = item.get("title", "")
            year = item.get("year")
            media_type = item.get("type", "movie")

            if not title:
                continue

            # Try to resolve TMDB ID
            tmdb_id = await _resolve_tmdb_id(tmdb_client, title, media_type, year)
            if not tmdb_id:
                summary["errors"].append(f"Could not resolve TMDB ID for: {title}")
                continue

            folder_name = f"{_safe_folder(title)} [{tmdb_id}]"

            await upsert_media_item(
                tmdb_id=tmdb_id,
                title=title,
                year=year,
                media_type=media_type,
                folder_name=folder_name,
            )
            summary["library_items_migrated"] += 1

        except Exception as exc:
            summary["errors"].append(f"Library item '{item.get('title', '?')}': {exc}")

    # Back up the old file
    backup = library_json.with_suffix(".json.bak")
    try:
        library_json.rename(backup)
        logger.info("Backed up library.json → library.json.bak")
    except Exception:
        pass


async def _scan_and_register(tmdb_client, summary: dict) -> None:
    """Scan existing directories and register items with TMDB IDs."""
    dir_pairs = [
        (Path(_OLD_MOVIES_DIR), "movie"),
        (Path(_OLD_TV_DIR), "tv"),
        (Path(_OLD_ANIME_DIR), "anime"),
    ]

    for base_dir, media_type in dir_pairs:
        if not base_dir.exists():
            continue

        for entry in sorted(base_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            # Check if already in new format
            m = _TMDB_ID_RE.match(entry.name)
            if m:
                continue  # Already migrated

            # Check for video files
            has_video = any(
                f.suffix.lower() in VIDEO_EXTENSIONS
                for f in entry.rglob("*") if f.is_file()
            )
            if not has_video:
                continue

            title, year = _parse_title_year(entry.name)
            tmdb_id = await _resolve_tmdb_id(tmdb_client, title, media_type, year)
            if not tmdb_id:
                summary["errors"].append(f"Could not resolve TMDB ID for folder: {entry.name}")
                continue

            folder_name = f"{_safe_folder(title)} [{tmdb_id}]"
            await upsert_media_item(
                tmdb_id=tmdb_id,
                title=title,
                year=year,
                media_type=media_type,
                folder_name=folder_name,
            )
            summary["library_items_migrated"] += 1


def _parse_title_year(name: str) -> tuple[str, Optional[int]]:
    m = _PAREN_YEAR.match(name)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return name.strip(), None


async def _resolve_tmdb_id(tmdb_client, title: str, media_type: str, year: Optional[int]) -> Optional[int]:
    """Resolve a title to a TMDB ID using the TMDB client."""
    if not tmdb_client:
        return None

    try:
        is_tv = media_type in ("tv", "anime")
        endpoint = "search/tv" if is_tv else "search/movie"
        title_key = "name" if is_tv else "title"

        # Search with year
        params = {"query": title, "include_adult": False}
        if year:
            date_key = "first_air_date_year" if is_tv else "year"
            params[date_key] = year

        data = await tmdb_client._get(endpoint, params=params)
        results = data.get("results", [])

        if not results and year:
            # Retry without year
            params.pop("first_air_date_year" if is_tv else "year", None)
            data = await tmdb_client._get(endpoint, params=params)
            results = data.get("results", [])

        if not results:
            # Try multi-search
            data = await tmdb_client._get("search/multi", params={"query": title, "include_adult": False})
            results = [r for r in data.get("results", []) if r.get("media_type") in ("movie", "tv")]

        if results:
            # Score by title match and popularity
            def score(r):
                r_title = (r.get("title") or r.get("name") or "").lower()
                return (r_title == title.lower(), r.get("popularity", 0))

            results.sort(key=score, reverse=True)
            return results[0]["id"]

        return None

    except Exception as exc:
        logger.warning("TMDB resolve failed for '%s': %s", title, exc)
        return None


# ── Step 2: Watch progress migration ────────────────────────────────────────

async def _migrate_watch_progress(summary: dict) -> None:
    """Migrate playback.json to watch_progress table."""
    progress_file = Path(settings.PROGRESS_FILE)
    if not progress_file.exists():
        return

    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            progress_data = json.load(f)
    except Exception as exc:
        summary["errors"].append(f"Could not read playback.json: {exc}")
        return

    # Build a mapping of folder path → tmdb_id from the media_items table
    folder_to_tmdb: dict[str, int] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tmdb_id, folder_name FROM media_items") as cur:
            for row in await cur.fetchall():
                folder_to_tmdb[row["folder_name"]] = row["tmdb_id"]

    # Also build a mapping from old directory paths
    old_dirs = [
        Path(_OLD_MOVIES_DIR), Path(_OLD_TV_DIR), Path(_OLD_ANIME_DIR),
        Path(_OLD_MOVIES_DIR_ARCHIVE), Path(_OLD_TV_DIR_ARCHIVE), Path(_OLD_ANIME_DIR_ARCHIVE),
    ]

    # Build a title-based lookup: extract title from folder_name for fuzzy matching
    title_to_tmdb: dict[str, int] = {}
    for folder_name, tid in folder_to_tmdb.items():
        m = _TMDB_ID_RE.match(folder_name)
        if m:
            title_to_tmdb[m.group(1).strip().lower()] = tid

    for file_path, progress in progress_data.items():
        try:
            fp = Path(file_path)
            position_ms = progress.get("position_ms", 0)
            duration_ms = progress.get("duration_ms", 0)

            # Find which media dir this file belongs to
            tmdb_id = None
            rel_path = None

            for base_dir in old_dirs:
                try:
                    rel = fp.relative_to(base_dir)
                    parts = rel.parts
                    if len(parts) >= 1:
                        folder_name = parts[0]
                        # Parse title from old folder name (e.g., "Inception (2010)" → "Inception")
                        parsed_title, _ = _parse_title_year(folder_name)

                        # Try exact folder name match first
                        if folder_name in folder_to_tmdb:
                            tmdb_id = folder_to_tmdb[folder_name]
                        else:
                            # Try title-based match
                            tmdb_id = title_to_tmdb.get(parsed_title.lower())

                        if tmdb_id:
                            # rel_path is the file path relative to the media folder
                            rel_path = str(Path(*parts[1:])) if len(parts) > 1 else fp.name
                    break
                except ValueError:
                    continue

            if tmdb_id and rel_path:
                await save_watch_progress(
                    tmdb_id=tmdb_id,
                    rel_path=rel_path,
                    position_ms=position_ms,
                    duration_ms=duration_ms,
                    watch_threshold=settings.WATCH_THRESHOLD,
                )
                summary["progress_entries_migrated"] += 1

        except Exception as exc:
            summary["errors"].append(f"Progress for '{file_path}': {exc}")

    # Back up the old file
    backup = progress_file.with_suffix(".json.bak")
    try:
        progress_file.rename(backup)
        logger.info("Backed up playback.json → playback.json.bak")
    except Exception:
        pass


# ── Step 3: Poster cache migration ──────────────────────────────────────────

async def _migrate_posters(summary: dict) -> None:
    """Rename poster files from 'Title (Year).jpg' to '{tmdb_id}.jpg'."""
    posters_dir = Path(settings.POSTERS_DIR)
    if not posters_dir.exists():
        return

    # Build mapping: title key → tmdb_id
    title_to_tmdb: dict[str, int] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tmdb_id, title, year FROM media_items") as cur:
            for row in await cur.fetchall():
                title = row["title"]
                year = row["year"]
                # Generate possible poster key variants
                if year:
                    key = _safe_poster_key(f"{title} ({year})")
                    title_to_tmdb[key.lower()] = row["tmdb_id"]
                key = _safe_poster_key(title)
                title_to_tmdb[key.lower()] = row["tmdb_id"]

    for poster_file in list(posters_dir.iterdir()):
        if not poster_file.is_file():
            continue
        if poster_file.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue

        # Check if already a numeric tmdb_id filename
        stem = poster_file.stem
        if stem.isdigit():
            continue

        # Try to match to a tmdb_id
        tmdb_id = title_to_tmdb.get(stem.lower())
        if tmdb_id:
            new_name = f"{tmdb_id}{poster_file.suffix}"
            new_path = posters_dir / new_name
            if not new_path.exists():
                try:
                    poster_file.rename(new_path)
                    summary["posters_renamed"] += 1
                except Exception as exc:
                    summary["errors"].append(f"Poster rename '{poster_file.name}' → '{new_name}': {exc}")
            else:
                # Target already exists, remove the old one
                try:
                    poster_file.unlink()
                    summary["posters_renamed"] += 1
                except Exception:
                    pass


# ── Step 4: Filesystem migration ────────────────────────────────────────────

async def _migrate_filesystem(summary: dict) -> None:
    """Move files from type-based directories into flat MEDIA_DIR/{Title} [{tmdb_id}]/ structure."""
    media_dir = Path(settings.MEDIA_DIR)
    archive_dir = Path(settings.ARCHIVE_DIR)

    # Build tmdb mapping for folders
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tmdb_id, title, year, type, folder_name FROM media_items") as cur:
            items = [dict(r) for r in await cur.fetchall()]

    # Map from old folder names to new folder names + tmdb info
    title_to_item: dict[str, dict] = {}
    for item in items:
        title = item["title"]
        year = item["year"]
        # Old folder name variants
        if year:
            old_key = f"{_safe_folder(title)} ({year})"
        else:
            old_key = _safe_folder(title)
        title_to_item[old_key.lower()] = item
        title_to_item[_safe_folder(title).lower()] = item

    # Process each old directory pair
    old_dir_pairs = [
        (Path(_OLD_MOVIES_DIR), "movie"),
        (Path(_OLD_TV_DIR), "tv"),
        (Path(_OLD_ANIME_DIR), "anime"),
    ]
    old_archive_pairs = [
        (Path(_OLD_MOVIES_DIR_ARCHIVE), "movie"),
        (Path(_OLD_TV_DIR_ARCHIVE), "tv"),
        (Path(_OLD_ANIME_DIR_ARCHIVE), "anime"),
    ]

    # Move primary media
    for old_dir, media_type in old_dir_pairs:
        if not old_dir.exists():
            continue
        # Skip if old_dir IS the new media_dir (same path)
        try:
            if old_dir.resolve() == media_dir.resolve():
                continue
        except Exception:
            pass

        await _move_dir_contents(old_dir, media_dir, title_to_item, summary)

    # Move archive media
    for old_dir, media_type in old_archive_pairs:
        if not old_dir.exists():
            continue
        try:
            if old_dir.resolve() == archive_dir.resolve():
                continue
        except Exception:
            pass

        await _move_dir_contents(old_dir, archive_dir, title_to_item, summary)


async def _move_dir_contents(
    src_dir: Path, dest_base: Path, title_to_item: dict, summary: dict
) -> None:
    """Move media folders from src_dir into dest_base with new naming."""
    if not src_dir.exists():
        return

    for entry in list(src_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        # Already in new format?
        if _TMDB_ID_RE.match(entry.name):
            # Just move to new location if needed
            dest = dest_base / entry.name
            if entry.resolve() != dest.resolve() and not dest.exists():
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(entry), str(dest))
                    summary["files_moved"] += 1
                except Exception as exc:
                    summary["errors"].append(f"Move '{entry}' → '{dest}': {exc}")
            continue

        # Look up the new folder name
        item = title_to_item.get(entry.name.lower())
        if not item:
            # Try without year
            name_no_year = _PAREN_YEAR.sub(r"\1", entry.name).strip()
            item = title_to_item.get(name_no_year.lower())

        if not item:
            summary["errors"].append(f"No TMDB mapping for folder: {entry.name}")
            continue

        new_folder_name = item["folder_name"]
        dest = dest_base / new_folder_name

        if entry.resolve() == dest.resolve():
            continue

        try:
            dest.mkdir(parents=True, exist_ok=True)

            # Move video files, flattening season subdirectories for TV
            for f in entry.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in VIDEO_EXTENSIONS:
                    # Also move subtitles
                    if f.suffix.lower() not in {".srt", ".ass", ".sub", ".idx", ".vtt", ".nfo"}:
                        continue

                # For TV episodes, flatten into show folder with SxxExx prefix
                rel = f.relative_to(entry)
                ep_match = _EPISODE_RE.search(f.name)

                if ep_match:
                    # Episode file — use just the filename (SxxExx - Title.ext)
                    dest_file = dest / f.name
                else:
                    # Movie or non-episode — keep relative path
                    dest_file = dest / rel

                if dest_file.exists():
                    continue

                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dest_file))
                summary["files_moved"] += 1

            # Clean up empty source directory
            _remove_empty_tree(entry)

        except Exception as exc:
            summary["errors"].append(f"Filesystem move '{entry.name}' → '{new_folder_name}': {exc}")


def _remove_empty_tree(path: Path) -> None:
    """Remove directory tree if it contains no files."""
    if not path.exists():
        return
    has_files = any(f.is_file() for f in path.rglob("*"))
    if not has_files:
        try:
            shutil.rmtree(str(path))
        except Exception:
            pass


# ── Step 5: Config migration ────────────────────────────────────────────────

def _migrate_config(summary: dict) -> None:
    """Update .env to use new MEDIA_DIR/ARCHIVE_DIR settings."""
    # Infer MEDIA_DIR from the old dirs (common parent)
    media_dir = settings.MEDIA_DIR
    archive_dir = settings.ARCHIVE_DIR

    _set_env_key("MEDIA_DIR", media_dir)
    _set_env_key("ARCHIVE_DIR", archive_dir)

    logger.info("Config migrated: MEDIA_DIR=%s, ARCHIVE_DIR=%s", media_dir, archive_dir)


def _set_env_key(key: str, value: str) -> None:
    """Write a key=value pair to .env."""
    env_path = _ENV_FILE
    if not env_path.exists():
        env_path.touch()

    lines = env_path.read_text(encoding="utf-8").splitlines()
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

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
