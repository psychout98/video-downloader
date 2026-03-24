import { test as base, expect, Page } from '@playwright/test';

/** Mock API responses matching the TypeScript interfaces in src/api/client.ts */
export const mockData = {
  status: {
    status: 'ok',
    movies_dir: 'C:\\Media\\Movies',
    tv_dir: 'C:\\Media\\TV',
    anime_dir: 'C:\\Media\\Anime',
    mpc_be_url: 'http://localhost:13579',
  },

  jobs: [
    {
      id: 'job-1',
      query: 'Breaking Bad S01E01',
      title: 'Breaking Bad',
      year: 2008,
      imdb_id: 'tt0903747',
      type: 'tv',
      season: 1,
      episode: 1,
      status: 'downloading',
      progress: 0.45,
      size_bytes: 1_500_000_000,
      downloaded_bytes: 675_000_000,
      quality: '1080p',
      torrent_name: 'Breaking.Bad.S01E01.1080p.BluRay.x264',
      rd_torrent_id: 'rd-123',
      file_path: null,
      error: null,
      log: '',
      stream_data: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 'job-2',
      query: 'Inception',
      title: 'Inception',
      year: 2010,
      imdb_id: 'tt1375666',
      type: 'movie',
      season: null,
      episode: null,
      status: 'complete',
      progress: 1,
      size_bytes: 2_000_000_000,
      downloaded_bytes: 2_000_000_000,
      quality: '1080p',
      torrent_name: 'Inception.2010.1080p.BluRay',
      rd_torrent_id: 'rd-456',
      file_path: 'C:\\Media\\Movies\\Inception (2010)\\Inception.mkv',
      error: null,
      log: '',
      stream_data: null,
      created_at: new Date(Date.now() - 3600000).toISOString(),
      updated_at: new Date(Date.now() - 1800000).toISOString(),
    },
    {
      id: 'job-3',
      query: 'Bad Movie',
      title: 'Bad Movie',
      year: 2024,
      imdb_id: null,
      type: 'movie',
      season: null,
      episode: null,
      status: 'failed',
      progress: 0,
      size_bytes: null,
      downloaded_bytes: 0,
      quality: null,
      torrent_name: null,
      rd_torrent_id: null,
      file_path: null,
      error: 'No cached streams found',
      log: '',
      stream_data: null,
      created_at: new Date(Date.now() - 7200000).toISOString(),
      updated_at: new Date(Date.now() - 7200000).toISOString(),
    },
  ],

  searchResult: {
    search_id: 'search-abc',
    media: {
      title: 'Breaking Bad',
      year: 2008,
      imdb_id: 'tt0903747',
      tmdb_id: 1396,
      type: 'tv',
      season: 1,
      episode: 1,
      is_anime: false,
      episode_titles: { 1: 'Pilot' },
      overview: 'A chemistry teacher diagnosed with terminal cancer teams up with a former student to manufacture crystal methamphetamine.',
      poster_path: null,
      poster_url: null,
    },
    streams: [
      {
        index: 0,
        name: 'Breaking.Bad.S01E01.1080p.BluRay.x264-GROUP',
        info_hash: 'abc123',
        download_url: null,
        size_bytes: 1_500_000_000,
        seeders: 150,
        is_cached_rd: true,
        magnet: null,
        file_idx: null,
      },
      {
        index: 1,
        name: 'Breaking.Bad.S01E01.720p.WEB-DL',
        info_hash: 'def456',
        download_url: null,
        size_bytes: 800_000_000,
        seeders: 45,
        is_cached_rd: false,
        magnet: null,
        file_idx: null,
      },
    ],
    warning: null,
  },

  library: [
    {
      tmdb_id: 27205,
      title: 'Inception',
      year: 2010,
      type: 'movie' as const,
      path: 'C:\\Media\\Movies\\Inception (2010)',
      folder: 'Inception (2010)',
      folder_name: 'Inception (2010)',
      file_count: 1,
      size_bytes: 2_000_000_000,
      poster: null,
      modified_at: Date.now() / 1000,
      storage: 'primary',
    },
    {
      tmdb_id: 1396,
      title: 'Breaking Bad',
      year: 2008,
      type: 'tv' as const,
      path: 'C:\\Media\\TV\\Breaking Bad',
      folder: 'Breaking Bad',
      folder_name: 'Breaking Bad',
      file_count: 62,
      size_bytes: 90_000_000_000,
      poster: null,
      modified_at: Date.now() / 1000,
      storage: 'primary',
    },
    {
      tmdb_id: 1429,
      title: 'Attack on Titan',
      year: 2013,
      type: 'anime' as const,
      path: 'C:\\Media\\Anime\\Attack on Titan',
      folder: 'Attack on Titan',
      folder_name: 'Attack on Titan',
      file_count: 87,
      size_bytes: 120_000_000_000,
      poster: null,
      modified_at: Date.now() / 1000,
      storage: 'primary',
    },
  ],

  settings: {
    TMDB_API_KEY: 'tmdb-key-12345',
    REAL_DEBRID_API_KEY: 'rd-key-67890',
    MEDIA_DIR: 'C:\\Media',
    ARCHIVE_DIR: 'C:\\Media\\Archive',
    DOWNLOADS_DIR: 'C:\\Downloads',
    POSTERS_DIR: 'C:\\Media\\Posters',
    MPC_BE_URL: 'http://localhost:13579',
    MPC_BE_EXE: 'C:\\Program Files\\MPC-BE x64\\mpc-be64.exe',
    HOST: '0.0.0.0',
    PORT: '8000',
    MAX_CONCURRENT_DOWNLOADS: '3',
    WATCH_THRESHOLD: '0.9',
  },

  logs: [
    '2024-01-15 10:00:00 INFO  Server started on 0.0.0.0:8000',
    '2024-01-15 10:00:01 INFO  Library scan complete: 150 items',
    '2024-01-15 10:05:00 INFO  Search: Breaking Bad S01E01',
  ],
};

/** Set up all API route mocks on a page */
export async function mockAllApis(page: Page) {
  await page.route('**/api/status', (route) =>
    route.fulfill({ json: mockData.status }),
  );

  await page.route('**/api/jobs', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: { jobs: mockData.jobs } });
    }
    return route.continue();
  });

  await page.route('**/api/search', (route) =>
    route.fulfill({ json: mockData.searchResult }),
  );

  await page.route('**/api/download', (route) =>
    route.fulfill({
      json: { job_id: 'job-new', status: 'pending', message: 'Download started' },
    }),
  );

  await page.route('**/api/jobs/*/retry', (route) =>
    route.fulfill({ json: { message: 'Job re-queued' } }),
  );

  await page.route('**/api/jobs/*', (route) => {
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ json: { message: 'Job deleted' } });
    }
    return route.fulfill({ json: mockData.jobs[0] });
  });

  await page.route('**/api/library?**', (route) =>
    route.fulfill({
      json: { items: mockData.library, count: mockData.library.length },
    }),
  );

  await page.route('**/api/library/continue', (route) =>
    route.fulfill({ json: { items: [] } }),
  );

  await page.route('**/api/library/refresh', (route) =>
    route.fulfill({
      json: { renamed: 2, posters_fetched: 5, errors: [], total_items: 150 },
    }),
  );

  await page.route('**/api/settings', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ json: { ok: true, written: ['MOVIES_DIR'] } });
    }
    return route.fulfill({ json: mockData.settings });
  });

  await page.route('**/api/settings/test-rd', (route) =>
    route.fulfill({
      json: { ok: true, key_suffix: '...7890', username: 'testuser' },
    }),
  );

  await page.route('**/api/logs**', (route) =>
    route.fulfill({
      json: { lines: mockData.logs, total: mockData.logs.length },
    }),
  );

  // Abort SSE endpoint so NowPlayingTab falls back to polling immediately
  await page.route('**/api/mpc/stream', (route) => route.abort());

  await page.route('**/api/mpc/status', (route) =>
    route.fulfill({
      json: {
        reachable: false,
        file: null,
        filename: null,
        state: 'stopped',
        is_playing: false,
        is_paused: false,
        position_ms: 0,
        duration_ms: 0,
        position_str: '00:00',
        duration_str: '00:00',
        volume: 100,
        muted: false,
        media: null,
      },
    }),
  );
}

/**
 * Extended test fixture that automatically mocks all APIs before each test.
 * Use `test` from this module instead of `@playwright/test` for mocked tests.
 */
export const test = base.extend<{ mockApis: void }>({
  mockApis: [
    async ({ page }, use) => {
      await mockAllApis(page);
      await use();
    },
    { auto: true },
  ],
});

export { expect };
