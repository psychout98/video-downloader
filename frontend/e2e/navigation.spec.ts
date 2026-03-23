import { test, expect } from './fixtures';

/**
 * Feature 1: Navigation & App Shell
 *
 * 1.1  App loads with header showing "Media Downloader" and "Connected" status
 * 1.2  Default tab is Queue, showing "Search & Download"
 * 1.3  Clicking "Library" tab shows library search input (placeholder: "Search library...")
 * 1.4  Clicking "Now Playing" tab shows "MPC-BE not reachable" when player is offline
 * 1.5  Clicking "Queue" tab returns to search/download view
 * 1.6  When /api/status returns 500, app shows "Disconnected"
 */
test.describe('Feature 1: Navigation & App Shell', () => {
  test('1.1 — app loads with header showing "Media Downloader" and "Connected" status', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('h1')).toHaveText('Media Downloader');
    await expect(page.getByText('Connected')).toBeVisible();
  });

  test('1.2 — default tab is Queue, showing "Search & Download"', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Search & Download')).toBeVisible();
  });

  test('1.3 — clicking "Library" tab shows library search input', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: 'Library' }).click();
    await expect(page.getByPlaceholder('Search library...')).toBeVisible();
  });

  test('1.4 — clicking "Now Playing" tab shows "MPC-BE not reachable" when player is offline', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: 'Now Playing' }).click();
    await expect(page.getByText('MPC-BE not reachable')).toBeVisible();
  });

  test('1.5 — clicking "Queue" tab returns to search/download view', async ({ page }) => {
    await page.goto('/');

    // Navigate away first
    await page.getByRole('button', { name: 'Library' }).click();
    await expect(page.getByPlaceholder('Search library...')).toBeVisible();

    // Navigate back to Queue
    await page.getByRole('button', { name: 'Queue' }).click();
    await expect(page.getByText('Search & Download')).toBeVisible();
  });

  test('1.6 — when /api/status returns 500, app shows "Disconnected"', async ({ page }) => {
    await page.route('**/api/status', (route) =>
      route.fulfill({ status: 500, body: 'Server error' }),
    );

    await page.goto('/');
    await expect(page.getByText('Disconnected')).toBeVisible();
  });
});
