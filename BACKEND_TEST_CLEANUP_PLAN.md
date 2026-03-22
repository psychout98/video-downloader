# Backend Test Cleanup Plan

## Current State Summary

The test suite has **20 test files** with roughly **250+ test cases** across unit and integration tests. `pytest.ini` enforces `--cov-fail-under=100`, meaning 100% coverage is required. The tests broadly cover the right modules but have several structural issues and gaps when measured against the implementation plan's acceptance criteria.

---

## Problem 1: Duplicated & Scattered Coverage

Several behaviors are tested in multiple places with slightly different approaches, creating maintenance burden without adding confidence.

### What to consolidate

| Duplicated Area | Files Involved | Action |
|---|---|---|
| `save_progress` auto-marks watched at 85% threshold | `test_database.py` (TestWatchProgressOperations), `test_library.py` (TestProgressEndpoints) | **Keep the database-layer test** as the unit test. The router test should assert the HTTP contract only (status code + response shape), not re-verify the threshold math. |
| `get_continue_watching` logic (excludes zero, excludes fully watched) | `test_database.py` (3 tests), `test_library.py` (2 tests) | **Keep database tests** for the query logic. Router tests should just confirm the endpoint returns 200 + correct shape. |
| Folder name parsing (`_parse_folder_tmdb_id`) | `test_library_manager.py` (TestParseFolderTmdbId), `test_mpc_router_helpers.py` (TestResolveMediaContext exercises same regex) | Acceptable overlap — different concerns. **No change needed.** |
| Zero-duration edge case | `test_database.py`, `test_library.py` | **Remove from router tests** — this is a database-layer invariant. |

---

## Problem 2: Overly Lenient Assertions in Router Tests

Several integration tests accept wide status-code ranges instead of asserting a specific contract. This masks bugs.

### Tests to tighten

| Test | Current Assertion | Should Be |
|---|---|---|
| `test_open_by_tmdb_id_and_rel_path` | `status_code in (200, 404, 500)` | Should set up a real file in `tmp_path`, configure `MEDIA_DIR`, and assert exactly `200`. Add a separate test for missing file → `404`. |
| `test_open_with_playlist` | `status_code in (200, 404, 500)` | Same approach — set up files, assert `200`. |
| `test_next_episode_returns_200_or_404` | `status_code in (200, 404)` | Split into two tests: one with valid playing context → `200`, one without → `404`. |
| `test_prev_episode_returns_200_or_404` | Same | Same split. |
| `test_get_poster_valid_returns_image` | `status_code in (200, 404)` | Insert a media item in the DB so the endpoint can find it, then assert exactly `200` with correct `content-type: image/jpeg`. |

---

## Problem 3: Missing Acceptance Criteria Coverage

The implementation plan defines specific behaviors that have no corresponding test.

### Phase 1: Database + Config

| Acceptance Criterion | Status | Test to Add |
|---|---|---|
| `media_items` CRUD | ✅ Covered | — |
| `watch_progress` CRUD | ✅ Covered | — |
| `tmdb_id` is the stable key — progress survives archive moves | ✅ Covered (`test_progress_survives_conceptual_archive`) | — |
| `watched` computed at write time using `WATCH_THRESHOLD` | ✅ Covered | — |
| Config: `MEDIA_DIR` + `ARCHIVE_DIR` replace 6 old dirs | ✅ Covered | — |
| Config: `PROGRESS_FILE` removed | ❌ Missing | **Add test**: `Settings` object has no `PROGRESS_FILE` attribute |
| `progress_store.py` deleted | ❌ Missing | **Add test**: `import server.core.progress_store` should raise `ModuleNotFoundError` |
| `media_items.added_at` doesn't change on upsert update | ✅ Covered | — |
| Folder regex `^(.+?)\s*\[(\d+)\]$` correctly parses all examples | ⚠️ Partial | **Add**: test for colon-replaced titles (`Star Wars - A New Hope [11]`) |
| File naming: `S{NN}E{NN} - {Episode Title}.ext` sanitized | ⚠️ Partial | **Add**: test episode filename with colon in title gets sanitized |

### Phase 2: API Endpoints

| Acceptance Criterion | Status | Test to Add |
|---|---|---|
| `GET /api/library` with `?type=`, `?sort=`, `?search=` | ⚠️ Shape only | **Add**: seed DB with mixed types, assert filtering actually works end-to-end through the router (not just DB) |
| `GET /api/library/{tmdb_id}` returns `location: "media"\|"archive"\|"both"` | ❌ Missing | **Add test**: set up items in both dirs, assert `location` field in response |
| `GET /api/library/{tmdb_id}` returns `episodes[]` with `progress_pct` and `watched` | ⚠️ Partial (checks `episodes` exists) | **Add**: seed progress in DB, assert episode objects have `progress_pct`, `watched`, `size_bytes` |
| `GET /api/library/{tmdb_id}/poster` returns correct `content-type` | ❌ Missing | See "tighten" section above |
| `POST /api/library/refresh` returns `{added, updated, renamed, posters_fetched, errors[]}` | ⚠️ Partial (checks 3 of 5 fields) | **Add**: assert `added` and `updated` are also in response |
| `GET /api/progress/{tmdb_id}` returns items array | ✅ Covered | — |
| `POST /api/progress/{tmdb_id}/{rel_path}` returns `{ok, watched}` | ✅ Covered | — |
| `GET /api/library/continue` returns correct shape with episode metadata | ❌ Missing | **Add**: seed DB, assert each item has `tmdb_id, title, type, poster_url, rel_path, season, episode, episode_title, progress_pct, updated_at` |
| `GET /api/mpc/status` includes `media` context with `tmdb_id`, `title`, `type`, `poster_url`, `season`, `episode` | ⚠️ Partial (checks key exists, not full shape) | **Add**: assert all 6 sub-fields when `media` is not null |
| `GET /api/mpc/stream` returns SSE with `event: status` | ⚠️ Partial (checks content-type) | **Add**: read first SSE event, parse it, assert it has status fields |
| `POST /api/mpc/open` resolves absolute path from `tmdb_id + rel_path` internally | ❌ Untested (lenient assertions) | See "tighten" section |
| `POST /api/mpc/next` / `POST /api/mpc/prev` return `{ok, rel_path}` | ❌ Untested (lenient assertions) | See "tighten" section |

### Phase 3–5: Frontend / Migration (backend-relevant pieces)

| Acceptance Criterion | Status | Test to Add |
|---|---|---|
| `media_organizer` output path is `MEDIA_DIR/{Title} [{tmdb_id}]/...` | ✅ Covered | — |
| Anime type uses same folder logic as TV | ✅ Covered | — |
| Watch tracker archive: moves file from `MEDIA_DIR` to `ARCHIVE_DIR` | ✅ Covered | — |
| Watch tracker: progress key `(tmdb_id, rel_path)` unchanged after move | ✅ Covered | — |
| Watch tracker: cleans up empty folders after movie archive | ✅ Covered | — |
| Watch tracker: moves subtitle files alongside video | ✅ Covered | — |
| No Windows paths exposed to frontend | ⚠️ Partial (one assertion in `test_library.py`) | **Add**: check `/api/mpc/status` response doesn't contain `C:\` or `D:\` in any string field |

---

## Problem 4: Test Infrastructure Issues

### 4a. `test_client` fixture doesn't seed the database

The `test_client` fixture creates a `mock_database` but most router integration tests don't insert any data before making requests. This means:

- Library list/detail tests rely on `MockLibraryManager` (in-memory list) for the scan path, but the DB is empty, so any endpoint that queries the DB directly gets no results.
- Progress endpoint tests work because they write-then-read, but "continue watching" can't test the join with `media_items`.

**Fix**: Create a `seeded_database` fixture that inserts a standard set of media items and progress records. Use it for integration tests that need data.

### 4b. `conftest.py` mock classes are stale for some flows

`MockLibraryManager.scan()` returns `self._items` but the real `LibraryManager.scan()` now returns items with specific fields (`tmdb_id`, `folder_name`, `file_count`, `size_bytes`, `poster`, `added_at`, `location`, `modified_at`, `year`, `title`). The mock doesn't enforce this shape, so tests can pass even if the real code changes the field names.

**Fix**: Add a `_REQUIRED_ITEM_FIELDS` set and validate `set_items()` input in `MockLibraryManager`.

### 4c. Event loop fixture is deprecated

The `event_loop` session-scoped fixture in `conftest.py` is the old `pytest-asyncio <0.21` pattern. Modern `pytest-asyncio` with `asyncio_mode = auto` doesn't need it and will warn.

**Fix**: Remove the `event_loop` fixture. The `anyio_backend` fixture can also be removed since `asyncio_mode = auto` handles it.

---

## Problem 5: Missing Edge Case Tests

| Module | Missing Edge Case | Priority |
|---|---|---|
| `database.py` | `get_all_media_items(sort="size")` — the plan mentions `?sort=size` but no test covers it | Medium |
| `database.py` | `save_progress` when the foreign key `tmdb_id` doesn't exist in `media_items` — should it fail or silently work? | High |
| `library_manager.py` | Scan with MEDIA_DIR and ARCHIVE_DIR pointing to the same path | Low |
| `watch_tracker.py` | `_on_stopped` when `_max_pct` has no entry for the file (e.g., tracker restarted mid-playback) | Medium |
| `media_organizer.py` | `organize()` when destination file already exists (duplicate download) | Medium |
| `mpc_client.py` | `_parse_variables` with malformed HTML (missing closing tags) | Low |
| `config.py` | Settings with `MEDIA_DIR` set to a non-existent path | Low |
| `routers/library.py` | `GET /api/library/{tmdb_id}` when `tmdb_id` is not a valid integer (string injection) | Medium |
| `routers/mpc.py` | `POST /api/mpc/command` with missing `command` field | Medium |
| `routers/jobs.py` | `POST /api/download` with negative `stream_index` | Low |

---

## Execution Order

### Step 1: Infrastructure fixes (do first, everything else depends on this)
1. Remove deprecated `event_loop` and `anyio_backend` fixtures from `conftest.py`
2. Add `_REQUIRED_ITEM_FIELDS` validation to `MockLibraryManager.set_items()`
3. Create `seeded_database` fixture with standard test data (Breaking Bad + Inception + partial progress)

### Step 2: Consolidate duplicate tests
1. In `test_library.py` (TestProgressEndpoints): simplify `test_post_progress_marks_watched_at_threshold`, `test_post_progress_not_watched_below_threshold`, and `test_post_progress_handles_zero_duration` to only assert the HTTP response shape — remove assertions about the threshold math itself
2. In `test_library.py` (TestContinueWatchingEndpoint): these are fine as-is (just shape checks)

### Step 3: Tighten lenient assertions
1. `test_mpc.py`: Rewrite `TestMpcOpenEndpoint` — set up files, configure mock settings, assert exact status codes
2. `test_mpc.py`: Split `TestMpcNextPrevEndpoints` into success and failure scenarios
3. `test_library.py`: Fix `test_get_poster_valid_returns_image` to insert a DB record and assert `200` + `image/jpeg`

### Step 4: Add missing acceptance criteria tests
1. Add `test_config.py::TestSettings::test_no_progress_file_setting` — assert `Settings` has no `PROGRESS_FILE`
2. Add `test_library.py` tests for `location` field in detail endpoint response
3. Add `test_library.py` test for continue-watching item shape (all required fields)
4. Add `test_mpc.py` test for full `media` context shape in status response
5. Add `test_library.py` test for refresh response including all 5 fields
6. Add `test_library.py` tests that use `seeded_database` to verify filtering/sorting actually works through the router
7. Add `test_mpc.py` SSE test that reads and parses the first event

### Step 5: Add edge case tests
1. `test_database.py`: FK violation on `save_progress` with nonexistent `tmdb_id`
2. `test_media_organizer.py`: duplicate destination file handling
3. `test_watch_tracker.py`: `_on_stopped` with missing `_max_pct` entry
4. `test_database.py`: `sort="size"` parameter

### Step 6: Verify and finalize
1. Run full test suite with coverage — confirm still at 100%
2. Review any new source lines not covered and add targeted tests
3. Ensure no test depends on execution order (each test is self-contained)

---

## Files to Modify

| File | Changes |
|---|---|
| `tests/conftest.py` | Remove `event_loop`/`anyio_backend`, add `seeded_database` fixture, validate mock item shapes |
| `tests/test_config.py` | Add `test_no_progress_file_setting` |
| `tests/test_database.py` | Add FK edge case, `sort="size"` test |
| `tests/test_library.py` | Tighten poster test, add location/shape/filtering tests, simplify duplicate threshold assertions |
| `tests/test_mpc.py` | Rewrite open/next/prev with proper setup, add media context shape test, add SSE event parsing test |
| `tests/test_media_organizer.py` | Add duplicate destination test |
| `tests/test_watch_tracker.py` | Add missing `_max_pct` edge case |
| `tests/test_database_extra.py` | No changes needed |
| `tests/test_library_manager.py` | Add colon-in-title folder parsing test |
| `tests/test_library_manager_extra.py` | No changes needed |
| `tests/test_library_router_helpers.py` | No changes needed |
| `tests/test_mpc_router_helpers.py` | No changes needed |
| `tests/test_mpc_client.py` | No changes needed |
| `tests/test_realdebrid_client.py` | No changes needed |
| `tests/test_torrentio_client.py` | No changes needed |
| `tests/test_tmdb_client.py` | No changes needed |
| `tests/test_base_client.py` | No changes needed |
| `tests/test_settings.py` | No changes needed |
| `tests/test_settings_router_helpers.py` | No changes needed |
| `tests/test_system.py` | No changes needed |
| `tests/test_jobs.py` | No changes needed |
| `tests/test_job_processor.py` | No changes needed |
