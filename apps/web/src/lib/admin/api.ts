import { ApiError, OfflineError } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'admin_access_token';
const EXPIRES_KEY = 'admin_access_token_expires_at';

type FetchOptions = RequestInit & {
  params?: Record<string, string | number | undefined>;
};

function isOfflineError(err: unknown): boolean {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true;
  if (err instanceof TypeError && /failed to fetch|network|load failed/i.test(err.message)) {
    return true;
  }
  return false;
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

function getExpiresAt(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(EXPIRES_KEY);
}

function setToken(token: string, expiresAt: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRES_KEY, expiresAt);
}

function clearToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRES_KEY);
}

function isAuthenticated(): boolean {
  const token = getToken();
  const expiresAt = getExpiresAt();
  if (!token || !expiresAt) return false;
  try {
    return new Date(expiresAt).getTime() > Date.now();
  } catch {
    return false;
  }
}

async function request<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { params, headers: customHeaders, ...rest } = options;

  let url = `${API_BASE}/api/admin${path}`;
  if (params) {
    const filtered: Record<string, string> = {};
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        filtered[key] = String(value);
      }
    }
    const qs = new URLSearchParams(filtered).toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(customHeaders as Record<string, string>),
  };

  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, { ...rest, headers });
  } catch (err) {
    if (isOfflineError(err)) {
      throw new OfflineError(path, (rest.method ?? 'GET').toUpperCase());
    }
    throw err;
  }

  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      clearToken();
      // Redirect to admin login on auth failure
      if (!window.location.pathname.endsWith('/admin')) {
        window.location.href = '/admin';
      }
    }

    const body = await response.json().catch(() => ({ error: { message: response.statusText } }));
    const requestId = response.headers.get('x-request-id');
    if (body && typeof body === 'object' && 'error' in body && body.error) {
      const envelope = body.error as {
        code?: string;
        message?: string;
        details?: Record<string, unknown>;
      };
      throw new ApiError(
        response.status,
        envelope.message ?? 'Unknown error',
        envelope.code ?? 'UNKNOWN',
        envelope.details ?? {},
        requestId,
      );
    }
    throw new ApiError(
      response.status,
      (body as { detail?: string }).detail ?? 'Unknown error',
      'UNKNOWN',
      {},
      requestId,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const adminApi = {
  get: <T>(path: string, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'POST', body: body ? JSON.stringify(body) : undefined }),

  put: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'PUT', body: body ? JSON.stringify(body) : undefined }),

  delete: <T>(path: string, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),

  setToken,
  clearToken,
  getToken,
  getExpiresAt,
  isAuthenticated,
};

export { ApiError, OfflineError };
