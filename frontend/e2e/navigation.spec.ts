import { test, expect } from './fixtures';

test.describe('Navigation', () => {
  test('app loads with header and connected status', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('h1')).toHaveText('Media Downloader');
    await expect(page.getByText('Connected')).toBeVisible();
  });

  test('tab navigation switches content', async ({ page }) => {
    await page.goto('/');

    // Default tab is Queue — search form visible
    await expect(page.getByText('Search & Download')).toBeVisible();

    // Switch to Library
    await page.getByRole('button', { name: 'Library' }).click();
    await expect(page.getByPlaceholder('Search library...')).toBeVisible();

    // Switch to Now Playing
    await page.getByRole('button', { name: 'Now Playing' }).click();
    await expect(page.getByText('MPC-BE not reachable')).toBeVisible();

    // Switch to Settings
    await page.getByRole('button', { name: 'Settings' }).click();
    await expect(page.getByText('Configuration')).toBeVisible();

    // Back to Queue
    await page.getByRole('button', { name: 'Queue' }).click();
    await expect(page.getByText('Search & Download')).toBeVisible();
  });

  test('shows disconnected status when server is down', async ({ page }) => {
    // Override status endpoint to fail
    await page.route('**/api/status', (route) =>
      route.fulfill({ status: 500, body: 'Server error' }),
    );

    await page.goto('/');
    await expect(page.getByText('Disconnected')).toBeVisible();
  });
});
