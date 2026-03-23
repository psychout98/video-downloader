import { test, expect, mockData } from './fixtures';

/**
 * Feature 2: Library Tab
 *
 * 2.1   Displays media cards for all library items (movies, TV, anime)
 * 2.2   Filter buttons (all, movies, tv, anime) show/hide cards by type
 * 2.3   Search input filters library items by title (case-insensitive)
 * 2.4   Shows "No results found." when search has no matches
 * 2.5   Clicking a media card opens a detail modal with the title as heading
 * 2.6   Modal fetches and displays episodes from /api/library/episodes
 * 2.7   Refresh Library button triggers /api/library/refresh and shows result
 * 2.8   Media cards show type badge (e.g. "movie") and year
 * 2.9   Modal lists episodes with Play, or Continue Watching / Start from Beginning if watched
 * 2.10  Episodes with watch history show a seek bar representing last playback position
 * 2.11  Top of modal has Continue Watching button (advances to next episode if current > 85%)
 */
test.describe('Feature 2: Library Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Library' }).click();
  });

  test('2.1 — displays media cards for all library items (movies, TV, anime)', async ({ page }) => {
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).toBeVisible();
    await expect(page.getByText('Attack on Titan')).toBeVisible();
  });

  test('2.2 — filter buttons (all, movies, tv, anime) show/hide cards by type', async ({ page }) => {
    // Movies only
    await page.getByRole('button', { name: 'movies' }).click();
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).not.toBeVisible();
    await expect(page.getByText('Attack on Titan')).not.toBeVisible();

    // TV only
    await page.getByRole('button', { name: 'tv' }).click();
    await expect(page.getByText('Breaking Bad')).toBeVisible();
    await expect(page.getByText('Inception')).not.toBeVisible();

    // Anime only
    await page.getByRole('button', { name: 'anime' }).click();
    await expect(page.getByText('Attack on Titan')).toBeVisible();
    await expect(page.getByText('Inception')).not.toBeVisible();

    // All
    await page.getByRole('button', { name: 'all' }).click();
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).toBeVisible();
    await expect(page.getByText('Attack on Titan')).toBeVisible();
  });

  test('2.3 — search input filters library items by title (case-insensitive)', async ({ page }) => {
    await page.getByPlaceholder('Search library...').fill('inception');
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).not.toBeVisible();
    await expect(page.getByText('Attack on Titan')).not.toBeVisible();
  });

  test('2.4 — shows "No results found." when search has no matches', async ({ page }) => {
    await page.getByPlaceholder('Search library...').fill('nonexistent movie');
    await expect(page.getByText('No results found.')).toBeVisible();
  });

  test('2.5 — clicking a media card opens a detail modal with the title as heading', async ({ page }) => {
    await page.route('**/api/library/episodes**', (route) =>
      route.fulfill({
        json: {
          seasons: [{
            season: 1,
            episodes: [{
              season: 1, episode: 1, title: 'Pilot', filename: 'S01E01.mkv',
              path: '/media/tv/Breaking Bad/S01E01.mkv',
              size_bytes: 1_500_000_000, progress_pct: 0, position_ms: 0, duration_ms: 0,
            }],
          }],
        },
      }),
    );

    await page.getByText('Breaking Bad').click();
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();
  });

  test('2.6 — modal fetches and displays episodes from /api/library/episodes', async ({ page }) => {
    let episodesRequested = false;
    await page.route('**/api/library/episodes**', (route) => {
      episodesRequested = true;
      return route.fulfill({
        json: {
          seasons: [{
            season: 1,
            episodes: [{
              season: 1, episode: 1, title: 'Pilot', filename: 'S01E01.mkv',
              path: '/media/tv/Breaking Bad/S01E01.mkv',
              size_bytes: 1_500_000_000, progress_pct: 0, position_ms: 0, duration_ms: 0,
            }],
          }],
        },
      });
    });

    await page.getByText('Breaking Bad').click();
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();
    expect(episodesRequested).toBe(true);
    await expect(page.getByText('Pilot')).toBeVisible();
  });

  test('2.7 — Refresh Library button triggers /api/library/refresh and shows result', async ({ page }) => {
    await page.getByRole('button', { name: /Refresh Library/i }).click();
    await expect(page.getByText(/Refreshed: 2 renamed/)).toBeVisible();
  });

  test('2.8 — media cards show type badge and year', async ({ page }) => {
    await expect(page.getByText('movie').first()).toBeVisible();
    await expect(page.getByText('2010')).toBeVisible();
    await expect(page.getByText('2008')).toBeVisible();
  });

  test('2.9 — modal lists episodes with Play, or Continue Watching / Start from Beginning if watched', async ({ page }) => {
    await page.route('**/api/library/episodes**', (route) =>
      route.fulfill({
        json: {
          seasons: [{
            season: 1,
            episodes: [
              {
                season: 1, episode: 1, title: 'Pilot', filename: 'S01E01.mkv',
                path: '/media/tv/Breaking Bad/S01E01.mkv',
                size_bytes: 1_500_000_000, progress_pct: 0, position_ms: 0, duration_ms: 0,
              },
              {
                season: 1, episode: 2, title: "Cat's in the Bag...", filename: 'S01E02.mkv',
                path: '/media/tv/Breaking Bad/S01E02.mkv',
                size_bytes: 1_400_000_000, progress_pct: 45, position_ms: 1_620_000, duration_ms: 3_600_000,
              },
            ],
          }],
        },
      }),
    );

    await page.getByText('Breaking Bad').click();
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();

    // Unwatched episode — should have a "Play" button
    const pilotRow = page.locator('[data-episode="S01E01"]');
    await expect(pilotRow.getByRole('button', { name: /Play/i })).toBeVisible();

    // Partially watched episode — should have "Continue Watching" and "Start from Beginning"
    const ep2Row = page.locator('[data-episode="S01E02"]');
    await expect(ep2Row.getByRole('button', { name: /Continue Watching/i })).toBeVisible();
    await expect(ep2Row.getByRole('button', { name: /Start from Beginning/i })).toBeVisible();
  });

  test('2.10 — episodes with watch history show a seek bar representing last playback position', async ({ page }) => {
    await page.route('**/api/library/episodes**', (route) =>
      route.fulfill({
        json: {
          seasons: [{
            season: 1,
            episodes: [{
              season: 1, episode: 1, title: 'Pilot', filename: 'S01E01.mkv',
              path: '/media/tv/Breaking Bad/S01E01.mkv',
              size_bytes: 1_500_000_000, progress_pct: 50, position_ms: 1_800_000, duration_ms: 3_600_000,
            }],
          }],
        },
      }),
    );

    await page.getByText('Breaking Bad').click();
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();

    const episodeRow = page.locator('[data-episode="S01E01"]');
    await expect(
      episodeRow.locator('[data-testid="seek-bar"], .seek-bar, .progress-bar, [role="progressbar"]'),
    ).toBeVisible();
  });

  test('2.11 — top of modal has Continue Watching button (advances to next episode if current > 85%)', async ({ page }) => {
    await page.route('**/api/library/episodes**', (route) =>
      route.fulfill({
        json: {
          seasons: [{
            season: 1,
            episodes: [
              {
                season: 1, episode: 1, title: 'Pilot', filename: 'S01E01.mkv',
                path: '/media/tv/Breaking Bad/S01E01.mkv',
                size_bytes: 1_500_000_000,
                progress_pct: 90, position_ms: 3_240_000, duration_ms: 3_600_000,
              },
              {
                season: 1, episode: 2, title: "Cat's in the Bag...", filename: 'S01E02.mkv',
                path: '/media/tv/Breaking Bad/S01E02.mkv',
                size_bytes: 1_400_000_000, progress_pct: 0, position_ms: 0, duration_ms: 0,
              },
            ],
          }],
        },
      }),
    );

    await page.getByText('Breaking Bad').click();
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();

    // Episode 1 is past 85%, so Continue Watching should point to episode 2
    const continueBtn = page.locator('[data-testid="continue-watching"], .continue-watching').first();
    await expect(continueBtn).toBeVisible();
    await expect(continueBtn).toContainText(/S01E02|Episode 2|Cat/i);
  });
});
