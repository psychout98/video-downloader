# Media Downloader — Implementation Plan

## Decisions Summary

| Area | Decision |
|------|----------|
| Library layout | Netflix-style horizontal rows |
| Detail view | Dedicated full-page detail |
| MPC-BE integration | Keep MPC-BE, add SSE push |
| Now Playing features | Media art, draggable seek, next/prev episode, auto-reconnect |
| Storage backend | SQLite for all mutable state (library metadata + progress) |
| Library identity | `tmdb_id` as the stable key for every media item |
| File naming | `Title [tmdb_id]/` with `SxxExx - Episode Title.ext` inside |
| Filesystem layout | Single `Media/` dir, single `Archive/` dir (no type split) |
| Archive structure | Mirror — identical relative paths in both locations |
| API style | Clean REST with `tmdb_id` paths, no Windows paths exposed to frontend |

---

## 1. Filesystem Layout

### Current (6 directories, split by type)
```
C:\Users\Noah\Media\
  Movies\         ← primary NVMe
  TV Shows\
  Anime\
D:\Media\
  Movies\         ← archive SATA
  TV Shows\
  Anime\
```

### New (2 directories, flat)
```
C:\Users\Noah\Media\             ← MEDIA_DIR (primary NVMe)
  Inception [27205]\
    Inception (2010).mkv
  Breaking Bad [1396]\
    S01E01 - Pilot.mkv
    S01E02 - Cat's in the Bag.mkv
    S02E01 - Seven Thirty-Seven.mkv
  Attack on Titan [1429]\
    S01E01 - To You, in 2000 Years.mkv

D:\Media\                        ← ARCHIVE_DIR (SATA)
  Inception [27205]\
    Inception (2010).mkv
  Breaking Bad [1396]\
    S01E01 - Pilot.mkv
```

### Naming Conventions

**Folders:**
```
{Title} [{tmdb_id}]
```
Examples: `Inception [27205]`, `Breaking Bad [1396]`, `Attack on Titan [1429]`

**Movie files:**
```
{Title} ({Year}).ext
```
Example: `Inception (2010).mkv`

**Episode files:**
```
S{NN}E{NN} - {Episode Title}.ext
```
Example: `S01E01 - Pilot.mkv`, `S04E13 - Face Off.mkv`

**Rules:**
- tmdb_id in the folder name is the single source of truth for identity
- No season subfolders — episodes are flat inside the show folder, prefixed with `SxxExx`
- Colons in titles become ` - ` (e.g., `Star Wars - A New Hope [11]`)
- Characters illegal on Windows (`<>:"/\|?*`) are stripped or replaced
- The `[tmdb_id]` suffix is always the last element before the closing bracket

### Parsing

A regex like `^(.+?)\s*\[(\d+)\]$` extracts title and tmdb_id from any folder name. This is how the scanner maps filesystem → database identity.

---

## 2. SQLite Schema

### New tables (added to existing `media_downloader.db`)

```sql
-- Canonical media items (one row per movie or series)
CREATE TABLE media_items (
    tmdb_id       INTEGER PRIMARY KEY,   -- TMDB ID (stable, unique)
    title         TEXT    NOT NULL,       -- Clean display title
    year          INTEGER,               -- Release year
    type          TEXT    NOT NULL,       -- 'movie' | 'tv' | 'anime'
    overview      TEXT,                   -- TMDB synopsis
    poster_path   TEXT,                   -- TMDB poster path (e.g. /abc123.jpg)
    imdb_id       TEXT,                   -- IMDb ID if available
    folder_name   TEXT    NOT NULL,       -- Current folder name: "Title [tmdb_id]"
    added_at      TEXT    NOT NULL,       -- ISO timestamp of first discovery
    updated_at    TEXT    NOT NULL        -- ISO timestamp of last metadata refresh
);

-- Per-file watch progress (keyed by tmdb_id + relative path)
CREATE TABLE watch_progress (
    tmdb_id       INTEGER NOT NULL,
    rel_path      TEXT    NOT NULL,       -- Relative to media folder: "S01E01 - Pilot.mkv"
    position_ms   INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    watched       BOOLEAN NOT NULL DEFAULT 0,  -- True when position >= threshold
    updated_at    TEXT    NOT NULL,
    PRIMARY KEY (tmdb_id, rel_path),
    FOREIGN KEY (tmdb_id) REFERENCES media_items(tmdb_id)
);

-- Index for "continue watching" and "recently watched" queries
CREATE INDEX idx_progress_updated ON watch_progress(updated_at DESC);
CREATE INDEX idx_progress_watched ON watch_progress(watched, updated_at DESC);
```

### Why this works

- **tmdb_id is the stable key.** Renames, archive moves, and re-downloads don't break anything.
- **rel_path is relative to the media folder**, not absolute. `S01E01 - Pilot.mkv` is the same whether the folder lives in `Media/` or `Archive/`.
- **watched is an explicit boolean**, computed at write time when `position_ms / duration_ms >= WATCH_THRESHOLD`. No need to re-derive it on every query.
- **The poster cache** on disk uses `{tmdb_id}.jpg` as the filename. No more `Title (Year).jpg` fragility.
- **media_items.folder_name** is denormalized for quick filesystem lookups but the canonical identity is always `tmdb_id`.

### Migration from current data

One-time migration script on first startup:
1. Read existing `data/library.json` entries
2. For each entry, resolve tmdb_id via TMDB API (or parse from folder if already renamed)
3. Insert into `media_items`
4. Read existing `data/playback.json`
5. For each absolute-path entry, find the matching media_item by path prefix, compute rel_path, insert into `watch_progress`
6. Rename `playback.json` → `playback.json.bak` and `library.json` → `library.json.bak`

---

## 3. Config Changes

### Current `.env` keys
```
MOVIES_DIR, TV_DIR, ANIME_DIR
MOVIES_DIR_ARCHIVE, TV_DIR_ARCHIVE, ANIME_DIR_ARCHIVE
POSTERS_DIR, PROGRESS_FILE
```

### New `.env` keys
```
MEDIA_DIR=C:\Users\Noah\Media
ARCHIVE_DIR=D:\Media
POSTERS_DIR=data/posters        # unchanged (but now keyed by tmdb_id)
WATCH_THRESHOLD=0.85            # unchanged
```

Six directory settings collapse to two. `PROGRESS_FILE` is removed (progress is in SQLite now).

---

## 4. Server-Side Changes

### Files to rewrite

| File | What changes |
|------|-------------|
| `server/config.py` | Replace 6 dir settings with `MEDIA_DIR` + `ARCHIVE_DIR`. Remove `PROGRESS_FILE`. |
| `server/core/library_manager.py` | Scan single `MEDIA_DIR`. Parse `[tmdb_id]` from folder names. Read/write `media_items` table instead of `library.json`. |
| `server/core/progress_store.py` | **Delete.** Replace with SQLite queries in `database.py`. |
| `server/core/watch_tracker.py` | Archive moves from `MEDIA_DIR/folder/` to `ARCHIVE_DIR/folder/`. Progress writes use `(tmdb_id, rel_path)`. |
| `server/core/media_organizer.py` | Output path becomes `MEDIA_DIR/{Title} [{tmdb_id}]/...` instead of type-based directories. |
| `server/database.py` | Add `media_items` and `watch_progress` tables. Add query helpers. |
| `server/routers/library.py` | New endpoints (see API section). Episodes served from filesystem but identified by tmdb_id. |
| `server/routers/mpc.py` | Add SSE endpoint. File-matching logic to resolve playing file → tmdb_id. |
| `server/state.py` | Remove `progress_store`. |

### Files to add

| File | Purpose |
|------|---------|
| `server/core/migration.py` | One-time migration from JSON files + old directory structure |
| `server/routers/sse.py` | SSE endpoint for MPC-BE status push |

### Library scan flow (new)

```
1. List folders in MEDIA_DIR
2. For each folder, parse "Title [tmdb_id]" from folder name
3. Check media_items table:
   - If tmdb_id exists → update file_count, size, modified_at
   - If tmdb_id is new → insert with metadata from TMDB
4. List video files inside each folder
5. For episodes: parse SxxExx from filename
6. Return items joined with watch_progress for the frontend
```

### Watch tracker flow (new archive logic)

```
1. MPC-BE reports file path (e.g. C:\Users\Noah\Media\Breaking Bad [1396]\S01E01 - Pilot.mkv)
2. Parse tmdb_id from path: extract folder name → regex → 1396
3. Compute rel_path: S01E01 - Pilot.mkv
4. Save progress: UPDATE watch_progress SET position_ms=X WHERE tmdb_id=1396 AND rel_path='S01E01 - Pilot.mkv'
5. If position/duration >= WATCH_THRESHOLD:
   a. SET watched=1
   b. Move file: MEDIA_DIR/Breaking Bad [1396]/S01E01 - Pilot.mkv → ARCHIVE_DIR/Breaking Bad [1396]/S01E01 - Pilot.mkv
   c. For movies: move entire folder contents
   d. Clean up empty folders in MEDIA_DIR
```

Progress **survives the move** because the key is `(tmdb_id=1396, rel_path='S01E01 - Pilot.mkv')` — neither value changes.

---

## 5. API Design

### Library endpoints

```
GET  /api/library
     → { items: [{ tmdb_id, title, year, type, poster_url, file_count, size_bytes, added_at, ... }] }
     Query params: ?type=movie|tv|anime  ?sort=recent|title|size  ?search=query

GET  /api/library/{tmdb_id}
     → { tmdb_id, title, year, type, overview, poster_url, imdb_id, folder_name,
         file_count, size_bytes, location: "media"|"archive"|"both",
         episodes: [{ rel_path, season, episode, title, size_bytes, progress_pct, watched }] }

GET  /api/library/{tmdb_id}/poster
     → FileResponse (serves data/posters/{tmdb_id}.jpg)

POST /api/library/refresh
     → { added, updated, renamed, posters_fetched, errors[] }
```

### Progress endpoints

```
GET  /api/progress/{tmdb_id}
     → { items: [{ rel_path, position_ms, duration_ms, watched, updated_at }] }

GET  /api/progress/{tmdb_id}/{rel_path}
     → { position_ms, duration_ms, watched, updated_at }

POST /api/progress/{tmdb_id}/{rel_path}
     Body: { position_ms, duration_ms }
     → { ok: true, watched: bool }
```

### Continue Watching endpoint

```
GET  /api/library/continue
     → { items: [{ tmdb_id, title, type, poster_url, rel_path, season, episode,
                    episode_title, progress_pct, updated_at }] }
     Returns items with 0 < progress < WATCH_THRESHOLD, ordered by updated_at DESC
```

### MPC endpoints

```
GET  /api/mpc/status
     → { reachable, file, filename, state, is_playing, is_paused,
         position_ms, duration_ms, volume, muted,
         media: { tmdb_id, title, type, poster_url, season, episode } | null }
     The "media" field is resolved by matching the playing file path against the library.

GET  /api/mpc/stream
     → SSE stream: event: status, data: { ...same as /api/mpc/status }
     Pushes every ~500ms when state changes, every ~2s otherwise.

POST /api/mpc/command
     Body: { command: int, position_ms?: int }
     → { ok: bool }

POST /api/mpc/open
     Body: { tmdb_id: int, rel_path: string, playlist?: string[] }
     Resolves the absolute path from tmdb_id + rel_path internally.
     → { ok: bool, launched: bool }

POST /api/mpc/next
     → { ok: bool, rel_path: string }
     Advances to the next episode based on current playing context.

POST /api/mpc/prev
     → { ok: bool, rel_path: string }
```

### Existing endpoints (unchanged)

```
GET  /api/status                     — server health
POST /api/search                     — search for media
POST /api/download                   — start download job
GET  /api/jobs                       — list jobs
GET  /api/jobs/{id}                  — job detail
DELETE /api/jobs/{id}                — delete job
POST /api/jobs/{id}/retry            — retry job
GET  /api/settings                   — get settings
POST /api/settings                   — update settings
POST /api/settings/test-rd           — test Real-Debrid key
GET  /api/logs                       — server logs
```

---

## 6. Frontend Changes

### Component structure (new)

```
src/
  components/
    Library/
      LibraryTab.tsx          ← Netflix-style rows layout
      MediaRow.tsx            ← Horizontal scrollable row of posters
      MediaCard.tsx           ← Single poster card with progress badge
      MediaDetailPage.tsx     ← Full-page detail view (replaces MediaModal)
      ContinueWatchingRow.tsx ← Special row for in-progress items
    NowPlaying/
      NowPlayingTab.tsx       ← Redesigned with SSE, media art, controls
      SeekBar.tsx             ← Draggable seek bar with time tooltip
      MediaInfo.tsx           ← Poster + title + episode info display
      PlayerControls.tsx      ← Play/pause, stop, skip, next/prev episode
    Queue/
      QueueTab.tsx            ← Unchanged
    Settings/
      SettingsTab.tsx         ← Updated for MEDIA_DIR/ARCHIVE_DIR settings
  api/
    client.ts                 ← Updated types and endpoints
```

### Library tab — Netflix-style rows

```
┌──────────────────────────────────────────┐
│  🔍 Search        [All][Movies][TV][Anime]│
│                                          │
│  ▶ Continue Watching                     │
│  [■■■▶] [■■▶■] [■■■▶]  →               │
│                                          │
│  ★ Recently Added                        │
│  [■■■] [■■■] [■■■] [■■■]  →             │
│                                          │
│  🎬 Movies                               │
│  [■■■] [■■■] [■■■] [■■■]  →             │
│                                          │
│  📺 TV Shows                             │
│  [■■■] [■■■] [■■■] [■■■]  →             │
│                                          │
│  🎌 Anime                                │
│  [■■■] [■■■] [■■■] [■■■]  →             │
└──────────────────────────────────────────┘
```

**Rows:**
- **Continue Watching** — from `GET /api/library/continue`. Shows poster + progress bar overlay + episode label.
- **Recently Added** — all types, sorted by `added_at DESC`, limited to ~20.
- **Movies / TV Shows / Anime** — filtered by type, sorted by title.
- When a filter is active (e.g. "Movies"), only show relevant rows.
- When search is active, switch to a flat grid of results.

**Poster cards:**
- Aspect ratio 2:3 (movie poster)
- Progress bar at bottom of poster (green overlay) if partially watched
- Checkmark badge if fully watched
- Clicking navigates to detail page

### Detail page

```
┌──────────────────────────────────────────┐
│  ← Back to Library                       │
│                                          │
│  ┌──────┐  Title                         │
│  │      │  2008 · TV · 5 seasons         │
│  │poster│  ★ 9.5                         │
│  │      │  Synopsis text from TMDB...    │
│  └──────┘                                │
│                                          │
│  [▶ Play] [▶ Resume S03E07]             │
│                                          │
│  Season 1 (7 episodes)          ▼       │
│  ┌─ E01 Pilot          45m    ✓ ──────┐ │
│  ├─ E02 Cat's in the…  47m    ✓       │ │
│  ├─ E03 ...And the…    48m    ▶ 62%   │ │
│  └─ E04 Cancer Man     48m    ○       │ │
│                                          │
│  Season 2 (13 episodes)        ▶       │
│  Season 3 (13 episodes)        ▶       │
└──────────────────────────────────────────┘
```

For movies: no season accordion, just a "Play" / "Resume at XX:XX" button.

### Now Playing tab

```
┌──────────────────────────────────────────┐
│                                          │
│  ┌──────┐  Breaking Bad                  │
│  │      │  S03E07 - One Minute           │
│  │poster│  Season 3 · Episode 7          │
│  │      │                                │
│  └──────┘                                │
│                                          │
│  ═══════════●════════════════            │
│  23:41              47:12                │
│                                          │
│   ⏮  ◁30s  [ ▶ Pause ]  30s▷  ⏭       │
│                                          │
│  Vol: ═══════●═══  [🔇]                  │
│                                          │
│  Status: Playing · MPC-BE connected      │
└──────────────────────────────────────────┘
```

**SSE integration:**
- On mount, open `EventSource('/api/mpc/stream')`
- On each event, update state
- On disconnect, show reconnecting indicator with pulsing animation
- On reconnect, seamlessly resume

**Draggable seek bar:**
- `onMouseDown` / `onTouchStart` → start tracking
- `onMouseMove` / `onTouchMove` → update visual position + show time tooltip
- `onMouseUp` / `onTouchEnd` → commit seek via API
- Don't update from SSE while user is dragging

**Next / Prev episode:**
- Rendered only when media context shows a TV/anime type
- Calls `POST /api/mpc/next` or `/api/mpc/prev`
- Button shows next episode title on hover/long-press

---

## 7. Implementation Order

### Phase 1: Database + Config (no UI changes)
1. Add `media_items` and `watch_progress` tables to `database.py`
2. Update `config.py` — `MEDIA_DIR`, `ARCHIVE_DIR` (keep old settings as fallbacks)
3. Write migration script (`core/migration.py`)
4. Rewrite `library_manager.py` to scan single dir + read/write SQLite
5. Rewrite progress tracking in `watch_tracker.py` to use `(tmdb_id, rel_path)`
6. Delete `progress_store.py`
7. Update `media_organizer.py` to use new folder naming
8. Test: existing library still loads, progress still tracks

### Phase 2: API (backend endpoints, no UI changes yet)
1. Rewrite `routers/library.py` with new endpoints
2. Add `GET /api/library/continue`
3. Add `GET /api/library/{tmdb_id}` detail endpoint
4. Add SSE endpoint `GET /api/mpc/stream`
5. Add `POST /api/mpc/next` and `POST /api/mpc/prev`
6. Update `POST /api/mpc/open` to accept `tmdb_id` + `rel_path`
7. Update `GET /api/mpc/status` to include matched media context
8. Test: all endpoints return correct data

### Phase 3: Frontend — Library
1. Update `api/client.ts` types and endpoints
2. Build `MediaCard.tsx` with progress badge
3. Build `MediaRow.tsx` horizontal scroll container
4. Build `ContinueWatchingRow.tsx`
5. Rebuild `LibraryTab.tsx` as Netflix-style rows
6. Build `MediaDetailPage.tsx` (full-page, with season accordion)
7. Add routing/navigation between library and detail page
8. Remove `MediaModal.tsx`

### Phase 4: Frontend — Now Playing
1. Build `SeekBar.tsx` with drag support
2. Build `MediaInfo.tsx` (poster + title display)
3. Build `PlayerControls.tsx` (play/pause, skip, next/prev)
4. Rebuild `NowPlayingTab.tsx` with SSE and new components
5. Add reconnection logic with visual feedback

### Phase 5: Polish + Migration
1. Settings page updates for new directory config
2. Full migration testing (old installs → new format)
3. Poster cache migration (rename `Title (Year).jpg` → `{tmdb_id}.jpg`)
4. File rename migration (move files into new folder structure)
5. End-to-end test: download → organize → play → archive → progress survives
