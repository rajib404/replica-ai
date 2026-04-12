/**
 * Tests for the typed API client (`@/lib/api`).
 *
 * Mocks `global.fetch` to verify URL construction, header injection, error
 * envelope parsing, token refresh on 401, and the public api.* helpers.
 */

import { api } from '@/lib/api';

// ─── Helpers ─────────────────────────────────────────────

function makeJsonResponse(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
}

beforeEach(() => {
  // Reset localStorage between tests so token state doesn't leak
  window.localStorage.clear();
  // Reset fetch mock
  // @ts-expect-error -- jest types
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('api client', () => {
  describe('basic GET', () => {
    it('makes a GET request and returns parsed JSON', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(makeJsonResponse({ ok: true }));

      const result = await api.get<{ ok: boolean }>('/api/health');
      expect(result).toEqual({ ok: true });

      // @ts-expect-error -- jest mock
      const [url, init] = global.fetch.mock.calls[0];
      expect(url).toContain('/api/health');
      expect(init.method).toBe('GET');
      expect(init.headers['Content-Type']).toBe('application/json');
    });

    it('attaches the bearer token from localStorage', async () => {
      window.localStorage.setItem('access_token', 'test-token-123');
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(makeJsonResponse({ ok: true }));

      await api.get('/api/me');

      // @ts-expect-error -- jest mock
      const init = global.fetch.mock.calls[0][1];
      expect(init.headers['Authorization']).toBe('Bearer test-token-123');
    });
  });

  describe('error envelope', () => {
    it('throws ApiError with code/message from { error: {...} } envelope', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(
        makeJsonResponse(
          {
            error: {
              code: 'NOT_FOUND',
              message: 'Owner does not exist',
              details: { owner_id: '42' },
            },
          },
          { status: 404, headers: { 'x-request-id': 'req-abc' } },
        ),
      );

      await expect(api.get('/api/owners/42')).rejects.toMatchObject({
        name: 'ApiError',
        status: 404,
        code: 'NOT_FOUND',
        detail: 'Owner does not exist',
        requestId: 'req-abc',
        details: { owner_id: '42' },
      });
    });

    it('falls back to {detail} for legacy error shape', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(
        makeJsonResponse({ detail: 'old style error' }, { status: 400 }),
      );

      await expect(api.get('/api/anything')).rejects.toMatchObject({
        status: 400,
        detail: 'old style error',
        code: 'UNKNOWN',
      });
    });

    it('handles non-JSON error responses gracefully', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(
        new Response('plain text crash', { status: 500 }),
      );

      await expect(api.get('/api/boom')).rejects.toMatchObject({
        status: 500,
      });
    });
  });

  describe('automatic refresh on 401', () => {
    it('retries the original request after a successful refresh', async () => {
      window.localStorage.setItem('access_token', 'old-token');
      window.localStorage.setItem('refresh_token', 'refresh-token');

      // @ts-expect-error -- jest mock
      global.fetch
        // First call: original request returns 401
        .mockResolvedValueOnce(
          makeJsonResponse(
            { error: { code: 'AUTH_ERROR', message: 'expired' } },
            { status: 401 },
          ),
        )
        // Second call: refresh endpoint returns new tokens
        .mockResolvedValueOnce(
          makeJsonResponse({
            tokens: {
              access_token: 'new-access',
              refresh_token: 'new-refresh',
            },
          }),
        )
        // Third call: retry of the original request, now succeeds
        .mockResolvedValueOnce(makeJsonResponse({ ok: true }));

      const result = await api.get<{ ok: boolean }>('/api/me');
      expect(result).toEqual({ ok: true });
      expect(window.localStorage.getItem('access_token')).toBe('new-access');
    });

    it('throws when refresh fails', async () => {
      window.localStorage.setItem('access_token', 'old');
      window.localStorage.setItem('refresh_token', 'old-refresh');

      // @ts-expect-error -- jest mock
      global.fetch
        // Original request: 401
        .mockResolvedValueOnce(
          makeJsonResponse(
            { error: { code: 'AUTH_ERROR', message: 'expired' } },
            { status: 401 },
          ),
        )
        // Refresh: also 401
        .mockResolvedValueOnce(
          makeJsonResponse({ error: { message: 'invalid' } }, { status: 401 }),
        );

      await expect(api.get('/api/me')).rejects.toMatchObject({ status: 401 });
    });
  });

  describe('mutating helpers', () => {
    it('POST sends the body as JSON', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(makeJsonResponse({ id: 'x' }));

      await api.post('/api/things', { name: 'Alice' });

      // @ts-expect-error -- jest mock
      const init = global.fetch.mock.calls[0][1];
      expect(init.method).toBe('POST');
      expect(JSON.parse(init.body)).toEqual({ name: 'Alice' });
    });

    it('PUT sends the body as JSON', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(makeJsonResponse({}));
      await api.put('/api/things/x', { v: 1 });
      // @ts-expect-error -- jest mock
      expect(global.fetch.mock.calls[0][1].method).toBe('PUT');
    });

    it('DELETE makes a DELETE request', async () => {
      // @ts-expect-error -- jest mock
      global.fetch.mockResolvedValueOnce(makeJsonResponse({}));
      await api.delete('/api/things/x');
      // @ts-expect-error -- jest mock
      expect(global.fetch.mock.calls[0][1].method).toBe('DELETE');
    });
  });

  describe('token storage helpers', () => {
    it('setTokens stores both tokens in localStorage', () => {
      api.setTokens('access-1', 'refresh-1');
      expect(window.localStorage.getItem('access_token')).toBe('access-1');
      expect(window.localStorage.getItem('refresh_token')).toBe('refresh-1');
    });

    it('clearTokens removes both tokens and owner_id', () => {
      window.localStorage.setItem('access_token', 'a');
      window.localStorage.setItem('refresh_token', 'r');
      window.localStorage.setItem('owner_id', 'o');
      api.clearTokens();
      expect(window.localStorage.getItem('access_token')).toBeNull();
      expect(window.localStorage.getItem('refresh_token')).toBeNull();
      expect(window.localStorage.getItem('owner_id')).toBeNull();
    });

    it('getToken returns null when no token is set', () => {
      expect(api.getToken()).toBeNull();
    });

    it('getToken returns the stored token', () => {
      window.localStorage.setItem('access_token', 'tok');
      expect(api.getToken()).toBe('tok');
    });
  });
});
