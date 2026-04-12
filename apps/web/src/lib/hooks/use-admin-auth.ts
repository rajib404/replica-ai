'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminApi } from '@/lib/admin/api';

interface UseAdminAuthState {
  loading: boolean;
  authenticated: boolean;
  username: string | null;
  expiresAt: string | null;
  logout: () => void;
}

/**
 * Client-side guard hook for admin pages.
 * Reads the admin token from localStorage on mount.
 * Redirects to /admin if missing or expired.
 */
export function useAdminAuth(redirectTo: string = '/admin'): UseAdminAuthState {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);

  useEffect(() => {
    const ok = adminApi.isAuthenticated();
    if (!ok) {
      adminApi.clearToken();
      router.replace(redirectTo);
      return;
    }

    // Verify with backend and pull username from /auth/me
    let cancelled = false;
    adminApi
      .get<{ username: string; expires_at: string }>('/auth/me')
      .then((data) => {
        if (cancelled) return;
        setUsername(data.username);
        setExpiresAt(data.expires_at);
        setAuthenticated(true);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        adminApi.clearToken();
        router.replace(redirectTo);
      });

    return () => {
      cancelled = true;
    };
  }, [router, redirectTo]);

  const logout = () => {
    adminApi.clearToken();
    setAuthenticated(false);
    setUsername(null);
    setExpiresAt(null);
    router.replace(redirectTo);
  };

  return { loading, authenticated, username, expiresAt, logout };
}
