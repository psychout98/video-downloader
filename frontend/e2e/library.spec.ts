import { test, expect, mockData } from './fixtures';

test.describe('Library Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Library' }).click();
  });

  test('displays media cards', async ({ page }) => {
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).toBeVisible();
    await expect(page.getByText('Attack on Titan')).toBeVisible();
  });

  test('filters by media type', async ({ page }) => {
    // Filter to movies
    await page.getByRole('button', { name: 'movies' }).click();
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).not.toBeVisible();
    await expect(page.getByText('Attack on Titan')).not.toBeVisible();

    // Filter to TV
    await page.getByRole('button', { name: 'tv' }).click();
    await expect(page.getByText('Breaking Bad')).toBeVisible();
    await expect(page.getByText('Inception')).not.toBeVisible();

    // Filter to anime
    await page.getByRole('button', { name: 'anime' }).click();
    await expect(page.getByText('Attack on Titan')).toBeVisible();
    await expect(page.getByText('Inception')).not.toBeVisible();

    // Back to all
    await page.getByRole('button', { name: 'all' }).click();
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).toBeVisible();
    await expect(page.getByText('Attack on Titan')).toBeVisible();
  });

  test('search filters library items', async ({ page }) => {
    await page.getByPlaceholder('Search library...').fill('inception');
    await expect(page.getByText('Inception')).toBeVisible();
    await expect(page.getByText('Breaking Bad')).not.toBeVisible();
    await expect(page.getByText('Attack on Titan')).not.toBeVisible();
  });

  test('shows no results message when search has no matches', async ({ page }) => {
    await page.getByPlaceholder('Search library...').fill('nonexistent movie');
    await expect(page.getByText('No results found.')).toBeVisible();
  });

  test('clicking a media card opens detail modal', async ({ page }) => {
    // Mock episodes endpoint for the modal
    await page.route('**/api/library/episodes**', (route) =>
      route.fulfill({
        json: {
          seasons: [
            {
              season: 1,
              episodes: [
                {
                  season: 1,
                  episode: 1,
                  title: 'Pilot',
                  filename: 'S01E01.mkv',
                  path: 'C:\\Media\\TV\\Breaking Bad\\S01E01.mkv',
                  size_bytes: 1_500_000_000,
                  progress_pct: 0,
                  position_ms: 0,
                  duration_ms: 0,
                },
              ],
            },
          ],
        },
      }),
    );

    await page.getByText('Breaking Bad').click();
    // Modal should appear with title
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();
  });

  test('refresh button triggers library refresh', async ({ page }) => {
    await page.getByRole('button', { name: /Refresh Library/i }).click();
    await expect(page.getByText(/Refreshed: 2 renamed/)).toBeVisible();
  });

  test('shows media metadata on cards', async ({ page }) => {
    // Check type badges and year
    await expect(page.getByText('movie').first()).toBeVisible();
    await expect(page.getByText('2010')).toBeVisible();
    await expect(page.getByText('2008')).toBeVisible();
  });
});
