# Media Downloader — Full Rebuild Spec Plan

## Overview

Media Downloader is an HTPC media library automation system. It searches for movies/TV/anime via TMDB + Torrentio, downloads via Real-Debrid, organizes files into a Plex-compatible library, controls MPC-BE playback, tracks watch progress, and auto-archives watched content.

**Tech Stack:** Python 3.14 + FastAPI backend, React 18 + TypeScript + Vite + Tailwind frontend, C# WPF desktop app, SQLite database.

---

## 1. Database Schema

### `jobs`
| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| query | TEXT | Original search query |
| title | TEXT | Resolved media title |
| year | INTEGER | Release year |
| imdb_id | TEXT | IMDb identifier |
| type | TEXT | "movie", "tv", "anime" |
| season | INTEGER | Season number |
| episode | INTEGER | Episode number |
| status | TEXT | PENDING, SEARCHING, FOUND, ADDING_TO_RD, WAITING_FOR_RD, DOWNLOADING, ORGANIZING, COMPLETE, FAILED, CANCELLED |
| progress | REAL | 0.0–1.0 |
| size_bytes | INTEGER | Total file size |
| downloaded_bytes | INTEGER | Bytes downloaded so far |
| quality | TEXT | Human-readable quality |
| torrent_name | TEXT | Torrent name |
| rd_torrent_id | TEXT | Real-Debrid torrent ID |
| file_path | TEXT | Final library location |
| error | TEXT | Error message if failed |
| log | TEXT | Newline-delimited progress log |
| stream_data | TEXT | JSON: {media, stream} |
| created_at | TEXT | ISO 8601 |
| updated_at | TEXT | ISO 8601 |

### `media_items`
| Column | Type | Description |
|---|---|---|
| tmdb_id | INTEGER PK | TMDB ID |
| title | TEXT | Display title |
| year | INTEGER | Release year |
| type | TEXT | "movie", "tv", "anime" |
| overview | TEXT | Description |
| poster_path | TEXT | TMDB poster path |
| imdb_id | TEXT | IMDb identifier |
| folder_name | TEXT | "Title [tmdb_id]" |
| added_at | TEXT | ISO 8601 |
| updated_at | TEXT | ISO 8601 |

### `watch_progress`
| Column | Type | Description |
|---|---|---|
| tmdb_id | INTEGER FK | → media_items |
| rel_path | TEXT | Relative path from show folder |
| position_ms | INTEGER | Playback position |
| duration_ms | INTEGER | Total duration |
| watched | BOOLEAN | True when position ≥ 85% |
| updated_at | TEXT | ISO 8601 |
| PK | (tmdb_id, rel_path) | Composite |

---

## 2. API Endpoints

### Jobs (`/api`)

| Method | Path | Description |
|---|---|---|
| POST | /search | Search TMDB + Torrentio, return streams |
| POST | /download | Queue download from pre-selected stream |
| GET | /jobs | List all jobs (last 200) |
| GET | /jobs/{id} | Get single job |
| DELETE | /jobs/{id} | Cancel/delete job |
| POST | /jobs/{id}/retry | Re-queue failed/cancelled job |

### Library (`/api`)

| Method | Path | Description |
|---|---|---|
| GET | /library | Scan library dirs, return items + count |
| POST | /library/refresh | Normalize folders + fetch posters |
| GET | /library/poster | Serve cached poster image |
| GET | /library/poster/tmdb | Fetch poster from TMDB, cache, serve |
| GET | /library/episodes | List episodes grouped by season with progress |
| GET | /progress | Get playback progress for a file |
| POST | /progress | Save playback position |

### MPC Player (`/api/mpc`)

| Method | Path | Description |
|---|---|---|
| GET | /status | Current player state + media context |
| GET | /stream | SSE stream of real-time status (fallback: polling) |
| POST | /command | Send wm_command to MPC-BE |
| POST | /open | Open file by tmdb_id + rel_path |
| POST | /next | Skip to next episode |
| POST | /prev | Go to previous episode |

### Settings (`/api`)

| Method | Path | Description |
|---|---|---|
| GET | /settings | Read current settings |
| POST | /settings | Update .env settings (hot-reload) |
| GET | /settings/test-rd | Test Real-Debrid API key |

### System (`/api`)

| Method | Path | Description |
|---|---|---|
| GET | /status | Server health + config summary |
| GET | /logs | Tail server log file |

---

## 3. Acceptance Criteria (from tests)

### AC-1: TMDB Client

| # | Criteria |
|---|---|
| 1.1 | MediaInfo.poster_url builds correct TMDB image CDN URL; returns None when poster_path is None |
| 1.2 | MediaInfo.display_name includes "Title (Year)" for movies; "Title S##E##" for TV; "Title Season #" for season-only |
| 1.3 | parse_query extracts season/episode from "S01E03", "Season 2", "S03", "Episode 5" formats |
| 1.4 | parse_query strips trailing year "2010" and "(2010)" from query but preserves IMDb URLs |
| 1.5 | search() returns correct movie via multi-search; returns TV with season/episode; raises ValueError on no results |
| 1.6 | search() resolves IMDb URL to correct tmdb_id |
| 1.7 | get_episode_count returns count from API; returns 0 on failure |
| 1.8 | get_episode_title returns episode name from API; returns "" on failure |
| 1.9 | fuzzy_resolve returns (title, year, poster) via typed search; falls back to multi-search; shortens title on fallback; raises ValueError when all fail |

### AC-2: Torrentio Client

| # | Criteria |
|---|---|
| 2.1 | parse_size handles GB, MB, TB (case-insensitive); returns None on no match |
| 2.2 | parse_seeders extracts count; returns 0 on no match |
| 2.3 | build_url includes RD key for cached; excludes for uncached; uses series format for TV/anime; defaults episode to 1 |
| 2.4 | get_streams returns list with correct fields; returns empty on no imdb_id, API failure, or empty streams |

### AC-3: Real-Debrid Client

| # | Criteria |
|---|---|
| 3.1 | is_cached returns True/False correctly; returns False on API error |
| 3.2 | add_magnet returns torrent ID; raises RealDebridError on HTTP error or missing ID |
| 3.3 | select_all_files succeeds on 204; raises on failure |
| 3.4 | wait_until_downloaded returns links immediately if "downloaded"; raises on "error" status, timeout, or no links; invokes progress callback |
| 3.5 | unrestrict_link returns (URL, filesize); raises on HTTP error or missing URL |
| 3.6 | unrestrict_all returns list of (URL, size) tuples |
| 3.7 | download_magnet completes full pipeline: add → select → wait → unrestrict |

### AC-4: Job Processor

| # | Criteria |
|---|---|
| 4.1 | filename_from_url extracts filename, strips query params, decodes URL encoding; returns None for no extension, trailing slash, empty URL |
| 4.2 | is_video_url recognizes .mkv, .mp4; rejects .txt; works with query params |
| 4.3 | episode_from_filename extracts from S01E03, s02e10, E05, Ep03, anime "- 12" patterns, 3-digit episodes; returns None when no pattern |
| 4.4 | safe_poster_key strips Windows-illegal chars; leaves normal strings unchanged |
| 4.5 | save_poster returns early when poster_path is None; skips existing poster |
| 4.6 | cancel_job returns True and calls task.cancel() for active jobs; returns False for unknown |
| 4.7 | cleanup_staging removes matching files; handles nonexistent staging dir |

### AC-5: Database Operations

| # | Criteria |
|---|---|
| 5.1 | create_job returns dict with all fields |
| 5.2 | get_job returns None for missing ID; returns created job with all fields |
| 5.3 | update_job changes status, progress, and other fields |
| 5.4 | append_log adds lines with newlines |
| 5.5 | delete_job removes row; returns False for missing ID |
| 5.6 | get_all_jobs returns list ordered DESC by created_at; respects limit |
| 5.7 | get_pending_jobs returns only "pending" status ordered ASC by created_at |
| 5.8 | create_job stores stream_data JSON |
| 5.9 | JobStatus enum has all expected values |

### AC-6: Library Manager

| # | Criteria |
|---|---|
| 6.1 | scan returns empty list for empty dirs; caches results; bypasses cache with force=True; detects video files; cache expires after TTL |
| 6.2 | extract_title_year parses "(2024)", ".2024.", "- 2024" formats; returns None when no year; removes quality tags; handles multi-word titles and special chars |
| 6.3 | clean_title removes quality tags, replaces dots with spaces, removes brackets, collapses spaces, strips leading/trailing dots and dashes |
| 6.4 | safe_folder_name removes invalid chars (<>|?), replaces colon with dash, preserves alphanumeric |

### AC-7: Media Organizer

| # | Criteria |
|---|---|
| 7.1 | sanitize removes <>"/\|?*, replaces colon with dash, collapses spaces, strips dots/spaces, handles empty strings |
| 7.2 | pick_video_file picks largest video; returns None for empty dir; ignores non-video files; finds videos in subdirectories |
| 7.3 | Movie destination: `{MOVIES_DIR}/{Title} [{TMDB_ID}]/{Title} ({Year}).ext`; handles no year |
| 7.4 | TV/Anime destination: `{TV_DIR}/{Title} [{TMDB_ID}]/S##E## - {Episode Title}.ext`; handles no episode title; season pack keeps original name; default season=1 |
| 7.5 | organize moves file to destination; picks largest video from directory; raises FileNotFoundError when no videos; creates parent dirs; preserves extension; overwrites duplicates; sanitizes colons in titles |

### AC-8: Watch Tracker

| # | Criteria |
|---|---|
| 8.1 | parse_tmdb_id_from_path extracts [1396] from Windows and POSIX paths; returns None for no bracket ID; extracts first bracket; handles empty string |
| 8.2 | compute_rel_path extracts relative path from MEDIA_DIR and ARCHIVE_DIR; falls back to filename |
| 8.3 | remove_if_empty removes folder with no videos; keeps folder with videos; no error on nonexistent; checks subdirectories |
| 8.4 | move_folder_remnants moves non-video files; blocks if videos remain; handles nonexistent source |
| 8.5 | Lifecycle: init sets _running=False and _prev_file=None; stop sets _running=False |
| 8.6 | Tick: records progress while playing; triggers _on_stopped after 2 stopped polls; single poll only increments counter; file change triggers callback for old file; unreachable MPC counts as stopped; 2 unreachable triggers _on_stopped |
| 8.7 | Archive: moves file to ARCHIVE_DIR; moves subtitle files too; no error on nonexistent; skips file outside media_dir; cleans up empty source folder |
| 8.8 | On stopped: archives if ≥ threshold; does NOT archive if below threshold; clears state; handles missing _max_pct entry |

### AC-9: MPC Client

| # | Criteria |
|---|---|
| 9.1 | ms_to_str: 0→"0:00", 45000→"0:45", 125000→"2:05", 3661000→"1:01:01", negative→zero |
| 9.2 | MPCStatus: file/filepath fallback, filename from Windows/POSIX paths, explicit filename preferred, state defaults to 0, is_playing/is_paused, position/duration defaults to 0, volume defaults to 100, muted defaults to False, to_dict has all keys |
| 9.3 | parse_variables: JSON format, legacy OnVariable() format, HTML `<p>` format, URL-decoded filepatharg, empty dict on failure |
| 9.4 | get_status: reachable=True on success, reachable=False on connection error |
| 9.5 | Commands: play_pause(887), play(891), pause(892), stop(888), mute(909), volume_up(907), volume_down(908), seek(889+position) |
| 9.6 | ping: True on success, False on exception |
| 9.7 | open_file: True on success, False on exception |

### AC-10: Search API

| # | Criteria |
|---|---|
| 10.1 | Empty/whitespace query returns 422 |
| 10.2 | Valid query returns search_id, media, streams |
| 10.3 | search_id is a valid UUID |
| 10.4 | Each stream has index, name, info_hash, size_bytes, is_cached_rd |
| 10.5 | Search result cached in state.searches with expires |

### AC-11: Download API

| # | Criteria |
|---|---|
| 11.1 | Invalid search_id returns 404 |
| 11.2 | Valid request returns 201 with job_id and status="pending" |
| 11.3 | stream_index out of range returns 422 |
| 11.4 | Download creates job in database with status="pending" |

### AC-12: Jobs API

| # | Criteria |
|---|---|
| 12.1 | GET /jobs returns 200 with jobs array |
| 12.2 | Empty database returns empty list |
| 12.3 | GET /jobs/{id} returns 404 for unknown ID |
| 12.4 | GET /jobs/{id} returns full job details |
| 12.5 | DELETE /jobs/{id} returns 404 for missing ID |
| 12.6 | DELETE pending job sets status to "cancelled" |
| 12.7 | DELETE completed job removes it from DB |
| 12.8 | POST /jobs/{id}/retry returns 404 for missing ID |
| 12.9 | Retry failed/cancelled job resets to "pending" |
| 12.10 | Retry active/pending job returns 400 |

### AC-13: Library API

| # | Criteria |
|---|---|
| 13.1 | GET /library returns 200 with items array and count |
| 13.2 | Empty library returns count zero |
| 13.3 | ?force=true bypasses cache |
| 13.4 | Library items have standard fields |
| 13.5 | POST /library/refresh returns renamed, posters_fetched, errors, total_items |
| 13.6 | GET /library/poster returns 404 for missing file |
| 13.7 | GET /library/poster returns 400 for directory or non-image |
| 13.8 | Valid poster returns 200 with image content-type |
| 13.9 | GET /library/episodes returns seasons array |
| 13.10 | Episodes have season, episode, title, filename, path, progress fields |
| 13.11 | Nonexistent folder returns 404 |
| 13.12 | ?folder_archive parameter accepted |
| 13.13 | GET /progress returns empty dict for missing; POST saves progress |

### AC-14: Settings API

| # | Criteria |
|---|---|
| 14.1 | GET /settings returns all config keys as strings/numbers |
| 14.2 | POST returns ok=true and written list |
| 14.3 | Unknown setting key returns 400 |
| 14.4 | Surrounding quotes stripped from values |
| 14.5 | Multiple keys updated in one request |
| 14.6 | GET /settings/test-rd returns ok and key_suffix |
| 14.7 | Invalid RD key returns ok=false with graceful error handling |

### AC-15: System API

| # | Criteria |
|---|---|
| 15.1 | GET /status returns 200 with status="ok" |
| 15.2 | Status includes movies_dir, tv_dir, anime_dir config fields |
| 15.3 | GET /logs returns lines array |
| 15.4 | Default log limit is 200; supports ?lines param |

### AC-16: MPC Player Control API

| # | Criteria |
|---|---|
| 16.1 | GET /mpc/status returns all player fields |
| 16.2 | Status includes media context with TMDB fields |
| 16.3 | POST /mpc/command returns ok=true; supports position_ms for seek |
| 16.4 | POST /mpc/open returns 404 when file not found; supports playlist param |
| 16.5 | POST /mpc/next returns next episode or 404 |
| 16.6 | POST /mpc/prev returns 404 if nothing playing |
| 16.7 | GET /mpc/stream returns text/event-stream with status fields |
| 16.8 | No Windows paths (C:\, D:\) leaked in media context |

### AC-17: Frontend — App Shell

| # | Criteria |
|---|---|
| 17.1 | Renders header with "Media Downloader" title |
| 17.2 | Renders Queue, Library, Now Playing tab buttons |
| 17.3 | Queue tab shown by default |
| 17.4 | Shows "Disconnected" initially; "Connected" after successful status check; "Disconnected" on failure |
| 17.5 | Polls status every 30 seconds; clears interval on unmount |
| 17.6 | Tab navigation switches between Queue, Library, Now Playing |
| 17.7 | Library onPlay callback switches to Now Playing tab |
| 17.8 | Toast notifications: renders messages, supports error/info types, auto-dismisses after 5 seconds, stacks multiple |

### AC-18: Frontend — Queue Tab

| # | Criteria |
|---|---|
| 18.1 | Renders search input and button; button disabled when empty, enabled with text |
| 18.2 | Calls searchMedia on submit; shows warning toast for API warnings; error toast on failure |
| 18.3 | Renders job list from polling; shows "No jobs found" when empty |
| 18.4 | Status badges: success for complete, error for failed, info for downloading, accent for pending |
| 18.5 | Progress bar shows percentage for active jobs; not shown for completed |
| 18.6 | Delete job on button click; cancel active job; retry failed job resets to pending |
| 18.7 | Stream list renders torrent names, "RD Cached" badge, seeders count |
| 18.8 | Download button triggers downloadStream; success/error toast |
| 18.9 | Shows media poster when search result has poster_url |
| 18.10 | Shows "No streams found" when empty; "Searching..." during load |
| 18.11 | Job displays: query when title null, progress with bytes, error message, torrent_name |
| 18.12 | Job filters: all, active, done, failed (includes cancelled) |
| 18.13 | Search results show IMDb badge, type, overview, size, stream name |
| 18.14 | Search results paginated with 5/10/25 rows per page |
| 18.15 | Search results filterable by stream attributes |
| 18.16 | Inactive jobs have re-search shortcut |

### AC-19: Frontend — Library Tab

| # | Criteria |
|---|---|
| 19.1 | Renders grid from API data; shows "Library is empty" when empty |
| 19.2 | Items display title, type badge, year, size |
| 19.3 | Filter buttons for all/movies/tv/anime work correctly |
| 19.4 | Search filters by title (case-insensitive); shows "No results found" when no matches |
| 19.5 | Refresh button calls refreshLibrary then getLibrary; shows success/error toast; disabled while loading |
| 19.6 | Clicking item opens MediaModal; close button works |

### AC-20: Frontend — Media Modal

| # | Criteria |
|---|---|
| 20.1 | Movie: renders title, year badge, storage badge, folder, file count; no Episodes section; no getEpisodes call |
| 20.2 | Movie: Play button calls openInMpc; triggers onPlay+onClose on success; error toast on failure |
| 20.3 | Poster image when set; initial letter placeholder when no poster; handles null year |
| 20.4 | TV: fetches episodes with folder and archive params; shows "Loading episodes..." then seasons |
| 20.5 | TV: expands first season by default; collapse/expand on click |
| 20.6 | TV: progress bar when progress_pct > 0 |
| 20.7 | TV: play episode with playlist; callbacks + toast on success/failure |
| 20.8 | TV: single-episode playlist fallback when season group not found |
| 20.9 | Modal closes on backdrop click, × button; does NOT close on inner content click |
| 20.10 | Episodes with watch history show seek bar; Continue Watching button advances to next episode if current > 85% |

### AC-21: Frontend — Now Playing Tab

| # | Criteria |
|---|---|
| 21.1 | Error state: shows "MPC-BE not reachable" on API reject or reachable=false; help text displayed |
| 21.2 | Renders filename; shows "No file loaded" when null |
| 21.3 | Pause button when playing; Play button when paused |
| 21.4 | Volume level displayed; Mute/Unmute toggle |
| 21.5 | Playback controls: PAUSE, PLAY, STOP commands sent correctly; error toasts |
| 21.6 | Skip ±30 seconds with bounds capping (0 to duration) |
| 21.7 | Volume slider sends VOLUME_UP command; mute button sends TOGGLE_MUTE |
| 21.8 | Polls status after SSE fallback; cleans up on unmount |

### AC-22: Frontend — API Client

| # | Criteria |
|---|---|
| 22.1 | checkStatus fetches /api/status; throws on HTTP error with message |
| 22.2 | searchMedia POSTs to /api/search with query |
| 22.3 | downloadStream sends snake_case keys; returns job_id, status, message |
| 22.4 | getJobs unwraps jobs array from envelope; returns empty array |
| 22.5 | getLibrary unwraps items array; passes force parameter |
| 22.6 | getPosterUrl encodes path correctly with special characters |
| 22.7 | Error handling includes status code; handles JSON parse errors; propagates network errors; prioritizes detail over error |
| 22.8 | retryJob POSTs to /api/jobs/{id}/retry |
| 22.9 | getTmdbPoster includes title, optional year and type params |
| 22.10 | getEpisodes unwraps seasons; includes folder_archive when provided |
| 22.11 | getProgress fetches with path param; saveProgress POSTs progress data |
| 22.12 | getMpcStatus fetches status; sendMpcCommand sends command with optional position |
| 22.13 | openInMpc sends path with optional playlist |

### AC-23: Frontend — Utility Functions

| # | Criteria |
|---|---|
| 23.1 | formatSize: 0→"0 B", bytes, KB, MB, GB, TB all formatted correctly |
| 23.2 | formatMs: negative→"0:00", seconds, minutes:seconds, hours:minutes:seconds with zero padding |
| 23.3 | timeAgo: "just now" within 60s, "Xm ago", "Xh ago", "Xd ago", localized date for old |
| 23.4 | escapeHtml: escapes &, <, >, ", '; handles normal and empty strings |
| 23.5 | hashColor: returns valid HSL, deterministic, different inputs → different colors, handles empty/special/unicode |

### AC-24: E2E — Navigation

| # | Criteria |
|---|---|
| 24.1 | App loads with "Media Downloader" header and "Connected" status |
| 24.2 | Default tab is Queue showing "Search & Download" |
| 24.3 | Library tab shows search input |
| 24.4 | Now Playing tab shows "MPC-BE not reachable" when offline |
| 24.5 | Queue tab returns to search/download view |
| 24.6 | Shows "Disconnected" when /api/status returns 500 |

### AC-25: E2E — Library

| # | Criteria |
|---|---|
| 25.1 | Displays media cards for movies, TV, anime |
| 25.2 | Filter buttons show/hide cards by type |
| 25.3 | Search filters by title (case-insensitive) |
| 25.4 | "No results found" when search has no matches |
| 25.5 | Clicking card opens detail modal with title heading |
| 25.6 | Modal fetches and displays episodes |
| 25.7 | Refresh button triggers refresh and shows result toast |
| 25.8 | Cards show type badge and year |
| 25.9 | Episodes show Play, Continue Watching, or Start from Beginning based on watch status |
| 25.10 | Episodes with watch history show seek bar |
| 25.11 | Continue Watching button advances to next episode if current > 85% |

### AC-26: E2E — Queue

| # | Criteria |
|---|---|
| 26.1 | Search button disabled when empty |
| 26.2 | Search shows media info heading |
| 26.3 | Shows stream count |
| 26.4 | Streams show torrent name, cache status, seeders |
| 26.5 | Download click shows "Download started" toast |
| 26.6 | Queue shows existing jobs on load |
| 26.7 | Job filters: active→downloading, done→complete, failed→failed, all→everything |
| 26.8 | Failed jobs show error message and Retry button |
| 26.9 | Retry shows "Job re-queued" toast |
| 26.10 | Complete jobs have Delete button; clicking shows "Job deleted" toast |
| 26.11 | Active jobs show progress percentage and status |
| 26.12 | Search results paginated: 5, 10, 25 rows per page |
| 26.13 | Search results filterable by stream attributes |
| 26.14 | Inactive jobs have re-search/retry shortcut |

---

## 4. Core Services

### 4.1 JobProcessor
Background worker polling for PENDING jobs every 5s. Semaphore limits to MAX_CONCURRENT_DOWNLOADS (default 2). Pipeline per job:
1. Deserialize pre-selected stream + media from stream_data
2. Add magnet to Real-Debrid (or check cache)
3. Poll RD until downloaded (30-min timeout)
4. Stream download to staging dir (chunked, with progress)
5. Organize files into library (rename, move)
6. Fetch TMDB poster into cache
7. Mark COMPLETE or FAILED

### 4.2 LibraryManager
- Scan: walk configured dirs, extract titles/years, find video files
- Cache with TTL, force bypass
- Refresh: resolve canonical titles via TMDB, rename folders, fetch posters

### 4.3 MediaOrganizer
- Movies: `{DIR}/{Title} [{TMDB_ID}]/{Title} ({Year}).ext`
- TV/Anime: `{DIR}/{Title} [{TMDB_ID}]/S##E## - {Episode Title}.ext`
- Season packs keep original filename
- Sanitize Windows-illegal chars, default season=1

### 4.4 WatchTracker
Background polling MPC-BE every 5s:
- Track max position reached per file
- After 2 consecutive "stopped" polls, trigger _on_stopped
- File change triggers callback for previous file
- If watched ≥ 85%: archive to ARCHIVE_DIR (with subtitles), clean empty folders
- Clear state after callback

### 4.5 ProgressStore
JSON-based persistence of per-file playback progress (position_ms, duration_ms, updated_at).

---

## 5. External API Clients

### 5.1 TMDBClient
- Query parsing: extract season/episode from various formats
- Multi-search, movie search, TV search
- Auto-detect anime (genre 16 + keywords)
- fuzzy_resolve with fallback (typed → multi → shortened title)
- Episode count and title lookup

### 5.2 TorrentioClient
- Stremio addon integration
- Build URL for movie/TV/anime with optional RD key
- Parse size (GB/MB/TB) and seeders from stream info
- Default episode to 1 when None

### 5.3 RealDebridClient
- Full pipeline: add_magnet → select_all_files → wait_until_downloaded → unrestrict_link
- is_cached check
- 30-min download timeout
- Progress callback support

### 5.4 MPCClient
- get_status with multiple response format parsing (JSON, legacy JS, HTML)
- Commands: play(891), pause(892), play_pause(887), stop(888), seek(889), mute(909), volume_up(907), volume_down(908)
- Convenience: ping, open_file
- URL-decoded filepatharg

### 5.5 BaseClient
- HTTP retry with exponential backoff
- Shared by all API clients

---

## 6. Frontend Architecture

### Components
```
App.tsx                     — Tab routing, connection status polling, toast system
├── Queue/QueueTab.tsx      — Search form, stream list, job list with filters
├── Library/LibraryTab.tsx  — Media grid, search, filter buttons, refresh
│   └── Library/MediaModal.tsx — Detail view, episodes, play controls
└── NowPlaying/NowPlayingTab.tsx — Real-time player, seek, volume, next/prev
```

### API Client (`api/client.ts`)
Type-safe fetch wrappers for all endpoints. Snake_case conversion. Error handling with status codes.

### Utilities (`utils/format.ts`)
formatSize, formatMs, timeAgo, escapeHtml, hashColor

---

## 7. Configuration (`.env`)

```
TMDB_API_KEY, REAL_DEBRID_API_KEY
MEDIA_DIR, ARCHIVE_DIR, DOWNLOADS_DIR
WATCH_THRESHOLD (default 0.85)
MPC_BE_URL (default http://127.0.0.1:13579)
MPC_BE_EXE (path to mpc-be64.exe)
HOST (default 0.0.0.0), PORT (default 8000)
MAX_CONCURRENT_DOWNLOADS (default 2)
RD_POLL_INTERVAL (default 30)
```

---

## 8. File Naming Conventions

- **Folders:** `{Title} [{tmdb_id}]` (e.g., `Breaking Bad [1396]`)
- **Movies:** `{Title} ({Year}).ext` (e.g., `Inception (2010).mkv`)
- **Episodes:** `S{NN}E{NN} - {Episode Title}.ext` (e.g., `S01E01 - Pilot.mkv`)
- No season subfolders (flat structure)
- Colons → ` - `, strip <>"/\|?*

---

## 9. Implementation Order

### Phase 1: Foundation
1. Database schema + CRUD operations (AC-5)
2. Configuration/settings module (AC-14, AC-15)
3. BaseClient with retry/backoff

### Phase 2: External Clients
4. TMDBClient (AC-1)
5. TorrentioClient (AC-2)
6. RealDebridClient (AC-3)
7. MPCClient (AC-9)

### Phase 3: Core Services
8. MediaOrganizer (AC-7)
9. LibraryManager (AC-6)
10. JobProcessor (AC-4)
11. WatchTracker (AC-8)
12. ProgressStore

### Phase 4: API Routes
13. System router (AC-15)
14. Settings router (AC-14)
15. Jobs router — search + download + CRUD (AC-10, AC-11, AC-12)
16. Library router (AC-13)
17. MPC router (AC-16)

### Phase 5: Frontend
18. API client + types (AC-22)
19. Utility functions (AC-23)
20. App shell + tabs + toasts (AC-17)
21. QueueTab (AC-18)
22. LibraryTab + MediaModal (AC-19, AC-20)
23. NowPlayingTab (AC-21)

### Phase 6: E2E & Integration
24. E2E tests (AC-24, AC-25, AC-26)
25. WPF desktop app (if applicable)
26. CI/CD + installer

---

## 10. Test Strategy

- **Backend unit tests:** pytest + aiosqlite in-memory + httpx mock
- **Backend integration tests:** FastAPI TestClient with mocked state/DB
- **Frontend unit tests:** Vitest + @testing-library/react
- **Frontend E2E tests:** Playwright with mocked API routes
- **Coverage target:** 100% (enforced)
