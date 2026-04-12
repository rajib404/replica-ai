/**
 * E2E: First-time owner setup wizard.
 *
 * Walks through the four-step setup wizard, mocks the FastAPI /api/auth/setup
 * response via Playwright route interception, and verifies the user lands on
 * the success / dashboard state.
 */

import { test, expect } from '@playwright/test';

test.describe('Setup Wizard', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept the setup API call so the test doesn't depend on a running
    // backend
    await page.route('**/api/auth/setup', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          owner_id: 'owner-e2e-1',
          tokens: {
            access_token: 'fake-access',
            refresh_token: 'fake-refresh',
            token_type: 'bearer',
          },
          connect_url: 'http://localhost:8000/connect?token=fake',
          qr_code_base64:
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
        }),
      });
    });
  });

  test('completes the four-step setup flow', async ({ page }) => {
    await page.goto('/setup');

    // Step 1 — Welcome
    await expect(page.getByRole('heading', { name: /welcome/i })).toBeVisible();
    await page.getByRole('button', { name: /get started|next/i }).click();

    // Step 2 — About You
    await expect(page.getByRole('heading', { name: /about you/i })).toBeVisible();
    await page.getByLabel(/name/i).fill('Test Owner');
    await page.getByLabel(/email/i).fill('e2e@example.com');
    await page.getByRole('button', { name: /continue/i }).click();

    // Step 3 — Security
    await expect(
      page.getByRole('heading', { name: /security|verification/i }),
    ).toBeVisible();
    // Pick the secret word option (default) and enter a value
    const secretInput = page.locator('input[type="text"]').first();
    await secretInput.fill('mysecretword');
    await page.getByRole('button', { name: /complete|finish|create/i }).click();

    // Step 4 — Complete
    await expect(
      page.getByRole('heading', { name: /complete|done|all set/i }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('blocks Continue when the name field is empty', async ({ page }) => {
    await page.goto('/setup');
    await page.getByRole('button', { name: /get started|next/i }).click();

    // On the About You step with an empty name, Continue is disabled
    const continueBtn = page.getByRole('button', { name: /continue/i });
    await expect(continueBtn).toBeDisabled();

    // Once we type a name, it becomes enabled
    await page.getByLabel(/name/i).fill('Alice');
    await expect(continueBtn).toBeEnabled();
  });
});
