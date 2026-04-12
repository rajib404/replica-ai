'use client';

import { useEffect, useRef, useState } from 'react';

export type OnlineStatus = 'online' | 'offline' | 'degraded';

const HEALTH_PROBE_INTERVAL_MS = 30_000;
const HEALTH_PROBE_TIMEOUT_MS = 5_000;
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function probeHealth(): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), HEALTH_PROBE_TIMEOUT_MS);
    const resp = await fetch(`${API_BASE}/api/health`, {
      method: 'GET',
      cache: 'no-store',
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    return resp.ok;
  } catch {
    return false;
  }
}

export function useOnlineStatus(): OnlineStatus {
  const [status, setStatus] = useState<OnlineStatus>('online');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const evaluate = async () => {
      if (!navigator.onLine) {
        setStatus('offline');
        return;
      }
      const reachable = await probeHealth();
      setStatus(reachable ? 'online' : 'degraded');
    };

    const handleOnline = () => {
      setStatus('online');
      evaluate();
    };
    const handleOffline = () => setStatus('offline');

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Initial check.
    setStatus(navigator.onLine ? 'online' : 'offline');
    evaluate();

    intervalRef.current = setInterval(() => {
      // Only probe when the browser thinks we're online.
      if (navigator.onLine) evaluate();
    }, HEALTH_PROBE_INTERVAL_MS);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  return status;
}
