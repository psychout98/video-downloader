import { test, expect, mockData } from './fixtures';

test.describe('Queue Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('search form submits and shows results', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();

    // Media info appears in the search result heading
    await expect(page.getByRole('heading', { name: /Breaking Bad/ })).toBeVisible();

    // Stream options
    await expect(page.getByText('Available Streams (2)')).toBeVisible();
    await expect(page.getByText('Breaking.Bad.S01E01.1080p.BluRay.x264-GROUP')).toBeVisible();
    await expect(page.getByText('RD Cached')).toBeVisible();
    await expect(page.getByText('150 seeders')).toBeVisible();
    await expect(page.getByText(/720p\.WEB-DL/)).toBeVisible();
  });

  test('download button starts a job', async ({ page }) => {
    await page.getByPlaceholder(/Search for movies/i).fill('Breaking Bad S01E01');
    await page.getByRole('button', { name: 'Search' }).click();
    await expect(page.getByText('Available Streams (2)')).toBeVisible();

    // Click first download button
    await page.getByRole('button', { name: 'Download' }).first().click();

    // Toast notification
    await expect(page.getByText('Download started')).toBeVisible();
  });

  test('shows existing jobs in the queue', async ({ page }) => {
    // Jobs are loaded on mount
    await expect(page.getByText('Download Queue')).toBeVisible();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();
    await expect(page.getByText('Bad Movie')).toBeVisible();
  });

  test('job filter buttons work', async ({ page }) => {
    await expect(page.getByText('Download Queue')).toBeVisible();

    // Filter to active jobs only
    await page.getByRole('button', { name: 'active' }).click();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('Inception', { exact: true })).not.toBeVisible();

    // Filter to done jobs
    await page.getByRole('button', { name: 'done' }).click();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();
    await expect(page.getByText('Breaking Bad', { exact: true })).not.toBeVisible();

    // Filter to failed jobs
    await page.getByRole('button', { name: 'failed' }).click();
    await expect(page.getByText('Bad Movie')).toBeVisible();
    await expect(page.getByText('No cached streams found')).toBeVisible();

    // Back to all
    await page.getByRole('button', { name: 'all' }).click();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();
  });

  test('can retry a failed job', async ({ page }) => {
    // Filter to failed jobs to find the retry button
    await page.getByRole('button', { name: 'failed' }).click();
    await expect(page.getByText('Bad Movie')).toBeVisible();

    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByText('Job re-queued')).toBeVisible();
  });

  test('can delete a job', async ({ page }) => {
    // Complete jobs show Delete button
    await page.getByRole('button', { name: 'done' }).click();
    await expect(page.getByText('Inception', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByText('Job deleted')).toBeVisible();
  });

  test('active job shows progress bar', async ({ page }) => {
    await page.getByRole('button', { name: 'active' }).click();
    await expect(page.getByText('Breaking Bad', { exact: true })).toBeVisible();
    await expect(page.getByText('45%')).toBeVisible();
    await expect(page.getByText('downloading')).toBeVisible();
  });

  test('search button is disabled when input is empty', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Search' })).toBeDisabled();
  });
});
