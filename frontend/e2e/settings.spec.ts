import { test, expect } from './fixtures';

test.describe('Settings Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Settings' }).click();
  });

  test('loads settings form with grouped fields', async ({ page }) => {
    await expect(page.getByText('Configuration')).toBeVisible();

    // Check group headings
    await expect(page.getByText('API Keys')).toBeVisible();
    await expect(page.getByText('Media Directories')).toBeVisible();
    await expect(page.getByText('MPC-BE')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Server', exact: true })).toBeVisible();

    // Check some field labels
    await expect(page.getByText('MEDIA_DIR', { exact: true })).toBeVisible();
    await expect(page.getByText('MPC_BE_URL', { exact: true })).toBeVisible();
  });

  test('save button is disabled when no changes', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Save Settings' })).toBeDisabled();
  });

  test('modifying a field enables save and shows discard', async ({ page }) => {
    const mediaInput = page.locator('label:has-text("MEDIA_DIR") + input, label:has-text("MEDIA_DIR") ~ input').first();
    await mediaInput.fill('D:\\NewMedia');

    await expect(page.getByRole('button', { name: 'Save Settings' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Discard Changes' })).toBeVisible();
  });

  test('save settings shows success toast', async ({ page }) => {
    const mediaInput = page.locator('label:has-text("MEDIA_DIR") + input, label:has-text("MEDIA_DIR") ~ input').first();
    await mediaInput.fill('D:\\NewMedia');

    await page.getByRole('button', { name: 'Save Settings' }).click();
    await expect(page.getByText(/Settings saved/)).toBeVisible();
  });

  test('discard changes reverts modifications', async ({ page }) => {
    const mediaInput = page.locator('label:has-text("MEDIA_DIR") + input, label:has-text("MEDIA_DIR") ~ input').first();
    const originalValue = await mediaInput.inputValue();
    await mediaInput.fill('D:\\NewMedia');

    await page.getByRole('button', { name: 'Discard Changes' }).click();
    await expect(mediaInput).toHaveValue(originalValue);
    await expect(page.getByRole('button', { name: 'Save Settings' })).toBeDisabled();
  });

  test('test RD key button works', async ({ page }) => {
    await page.getByRole('button', { name: 'Test RD Key' }).click();
    await expect(page.getByText(/RD key valid/)).toBeVisible();
    await expect(page.getByText(/testuser/)).toBeVisible();
  });

  test('shows server logs section', async ({ page }) => {
    await expect(page.getByText('Server Logs')).toBeVisible();
    await expect(page.getByText(/Server started/)).toBeVisible();
  });

  test('API key fields are password type', async ({ page }) => {
    const tmdbInput = page.locator('label:has-text("TMDB_API_KEY") + input, label:has-text("TMDB_API_KEY") ~ input').first();
    await expect(tmdbInput).toHaveAttribute('type', 'password');
  });
});
