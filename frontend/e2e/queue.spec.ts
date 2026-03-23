import { test, expect, mockData } from './fixtures';

/**
 * Feature 3: Queue Tab — Search & Download
 *
 * 3.1   Search button is disabled when input is empty
 * 3.2   Submitting a search shows media info heading (e.g. "Breaking Bad")
 * 3.3   Search results show stream count ("Available Streams (2)")
 * 3.4   Stream results show torrent name, cache status ("RD Cached"), and seeders
 * 3.5   Clicking Download on a stream shows "Download started" toast
 * 3.6   Queue section ("Download Queue") shows all existing jobs on load
 * 3.7   Job filter buttons: active, done, failed, all
 * 3.8   Failed jobs show error message and a Retry button
 * 3.9   Clicking Retry shows "Job re-queued" toast
 * 3.10  Complete jobs show a Delete button; clicking it shows "Job deleted" toast
 * 3.11  Active jobs show progress percentage and status ("downloading")
 * 3.12  Search results are paginated with options for 5, 10, or 25 rows per page
 * 3.13  Search results are filterable by stream attributes
 * 3.14  Inactive jobs have a shortcut to re-search and retry with a different stream
 */
test.describe('Feature 3: Queue Tab — Search & Download', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('3.1 — search button is disabled when input is empty', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Search' })).toBeDisabled();
  });

  test('3.2 — submitting a search shows media info heading', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();

    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();
  });

  test('3.3 — search results show stream count', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();

    await expect(page.getByText('Available Streams (2)')).toBeVisible();
  });

  test('3.4 — stream results show torrent name, cache status, and seeders', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();

    await expect(page.getByText('Breaking.Bad.S01E01.1080p.BluRay.x264-GROUP')).toBeVisible();
    await expect(page.getByText('RD Cached')).toBeVisible();
    await expect(page.getByText('150 seeders')).toBeVisible();
    await expect(page.getByText(/720p\.WEB-DL/)).toBeVisible();
  });

  test('3.5 — clicking Download on a stream shows "Download started" toast', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();
    await expect(page.getByText('Available Streams (2)')).toBeVisible();

    await page.getByRole('button', { name: 'Download' }).first().click();
    await expect(page.getByText('Download started')).toBeVisible();
  });

  test('3.6 — queue section shows all existing jobs on load', async ({ page }) => {
    await expect(page.getByText('Download Queue')).toBeVisible();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();
    await expect(page.getByText('Bad Movie')).toBeVisible();
  });

  test('3.7 — job filter buttons: active shows downloading, done shows complete, failed shows failed, all shows everything', async ({ page }) => {
    await expect(page.getByText('Download Queue')).toBeVisible();

    // Active
    await page.getByRole('button', { name: 'active' }).click();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('Inception', { exact: true })).not.toBeVisible();

    // Done
    await page.getByRole('button', { name: 'done' }).click();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();
    await expect(page.getByText('Breaking Bad', { exact: true })).not.toBeVisible();

    // Failed
    await page.getByRole('button', { name: 'failed' }).click();
    await expect(page.getByText('Bad Movie')).toBeVisible();

    // All
    await page.getByRole('button', { name: 'all' }).click();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();
  });

  test('3.8 — failed jobs show error message and a Retry button', async ({ page }) => {
    await page.getByRole('button', { name: 'failed' }).click();
    await expect(page.getByText('Bad Movie')).toBeVisible();
    await expect(page.getByText('No cached streams found')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  });

  test('3.9 — clicking Retry shows "Job re-queued" toast', async ({ page }) => {
    await page.getByRole('button', { name: 'failed' }).click();
    await expect(page.getByText('Bad Movie')).toBeVisible();

    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByText('Job re-queued')).toBeVisible();
  });

  test('3.10 — complete jobs show Delete button; clicking it shows "Job deleted" toast', async ({ page }) => {
    await page.getByRole('button', { name: 'done' }).click();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByText('Job deleted')).toBeVisible();
  });

  test('3.11 — active jobs show progress percentage and status', async ({ page }) => {
    await page.getByRole('button', { name: 'active' }).click();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('45%')).toBeVisible();
    await expect(page.getByText('downloading')).toBeVisible();
  });

  test('3.12 — search results are paginated with options for 5, 10, or 25 rows per page', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();
    await expect(page.getByText('Available Streams')).toBeVisible();

    // Pagination controls should be visible with row-count options
    const paginator = page.locator('[data-testid="pagination"], .pagination, nav[aria-label*="pagination"]');
    await expect(paginator).toBeVisible();

    // Row-per-page selector should offer 5, 10, 25
    const rowSelector = page.locator('[data-testid="rows-per-page"], .rows-per-page, select');
    await expect(rowSelector).toBeVisible();
    await expect(page.getByRole('option', { name: '5' })).toBeAttached();
    await expect(page.getByRole('option', { name: '10' })).toBeAttached();
    await expect(page.getByRole('option', { name: '25' })).toBeAttached();
  });

  test('3.13 — search results are filterable by stream attributes', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();
    await expect(page.getByText('Available Streams')).toBeVisible();

    // Filter controls for stream attributes should be present
    const filters = page.locator('[data-testid="stream-filters"], .stream-filters');
    await expect(filters).toBeVisible();
  });

  test('3.14 — inactive jobs have a shortcut to re-search and retry with a different stream', async ({ page }) => {
    // Navigate to done or failed jobs
    await page.getByRole('button', { name: 'failed' }).click();
    await expect(page.getByText('Bad Movie')).toBeVisible();

    // There should be a re-search / "Try Different" shortcut
    const retrySearch = page.getByRole('button', { name: /search again|re-search|try different/i });
    await expect(retrySearch).toBeVisible();
  });
});
