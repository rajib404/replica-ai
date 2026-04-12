const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type FetchOptions = RequestInit & {
  params?: Record<string, string>;
};

class ApiError extends Error {
  public code: string;
  public details: Record<string, unknown>;
  public requestId: string | null;

  constructor(
    public status: number,
    public detail: string,
    code = 'UNKNOWN',
    details: Record<string, unknown> = {},
    requestId: string | null = null,
  ) {
    super(detail);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

class OfflineError extends Error {
  constructor(public path: string, public method: string) {
    super(`Offline: cannot reach ${method} ${path}`);
    this.name = 'OfflineError';
  }
}

function isOfflineError(err: unknown): boolean {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true;
  if (err instanceof TypeError && /failed to fetch|network|load failed/i.test(err.message)) {
    return true;
  }
  return false;
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('access_token');
}

function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('refresh_token');
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
}

function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('owner_id');
}

// Mutex to avoid concurrent refresh calls
let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const resp = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) return false;

    const data = await resp.json();
    setTokens(data.tokens.access_token, data.tokens.refresh_token);
    return true;
  } catch {
    return false;
  }
}

async function refreshIfNeeded(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = tryRefresh().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

async function request<T>(path: string, options: FetchOptions = {}, isRetry = false): Promise<T> {
  const { params, headers: customHeaders, ...rest } = options;

  let url = `${API_BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams(params).toString();
    url += `?${qs}`;
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
    // Auto-refresh on 401 (once)
    if (response.status === 401 && !isRetry) {
      const refreshed = await refreshIfNeeded();
      if (refreshed) {
        return request<T>(path, options, true);
      }
    }

    const body = await response.json().catch(() => ({ error: { message: response.statusText } }));
    const requestId = response.headers.get('x-request-id');
    // Preferred envelope: { error: { code, message, details } }
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
    // Legacy fallback for responses that still use { detail: "..." }
    throw new ApiError(
      response.status,
      (body as { detail?: string }).detail ?? 'Unknown error',
      'UNKNOWN',
      {},
      requestId,
    );
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'POST', body: JSON.stringify(body) }),

  put: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'PUT', body: JSON.stringify(body) }),

  delete: <T>(path: string, options?: FetchOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),

  setTokens,
  clearTokens,
  getToken,
  getRefreshToken,
  refreshIfNeeded,
  ApiError,
  OfflineError,
};

export { ApiError, OfflineError };
