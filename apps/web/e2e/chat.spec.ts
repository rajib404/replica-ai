/**
 * E2E: Authenticated chat conversation.
 *
 * Pre-seeds localStorage with a fake JWT, intercepts the FastAPI /api/chat/*
 * endpoints, and verifies that messages typed by the user appear in the
 * conversation, an assistant response is rendered, and the input clears.
 */

import { test, expect } from '@playwright/test';

const FAKE_JWT =
  'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvd25lci0xIiwicm9sZSI6Im93bmVyIiwidHlwZSI6ImFjY2VzcyJ9.fake';

test.describe('Chat conversation', () => {
  test.beforeEach(async ({ page }) => {
    // Seed auth state before the page loads
    await page.addInitScript(({ token }) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem('refresh_token', token);
      localStorage.setItem('owner_id', 'owner-1');
    }, { token: FAKE_JWT });

    // Mock empty thread list on first load
    await page.route('**/api/chat/threads*', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ threads: [], total: 0 }),
        });
        return;
      }
      await route.continue();
    });

    // Mock the chat send response
    await page.route('**/api/chat/message', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          thread_id: 'thread-e2e-1',
          message_id: 'msg-1',
          response: 'Hello! Nice to hear from you.',
          sources: [],
          is_learning: false,
        }),
      });
    });
  });

  test('user can send a message and see the assistant reply', async ({ page }) => {
    await page.goto('/dashboard/chat');

    const input = page.locator('textarea, input[type="text"]').last();
    await input.fill('Hi there!');
    await input.press('Enter');

    // The user message appears in the conversation
    await expect(page.getByText('Hi there!')).toBeVisible();

    // The assistant reply is rendered
    await expect(
      page.getByText(/nice to hear from you/i),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('input clears after sending', async ({ page }) => {
    await page.goto('/dashboard/chat');

    const input = page.locator('textarea, input[type="text"]').last();
    await input.fill('Test message');
    await input.press('Enter');

    await expect(input).toHaveValue('');
  });
});
