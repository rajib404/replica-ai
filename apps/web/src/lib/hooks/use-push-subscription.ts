'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import {
  clearCachedPushSubscription,
  getCachedPushSubscription,
  setCachedPushSubscription,
} from '@/lib/pwa/db';

type PermissionState = 'default' | 'granted' | 'denied' | 'unsupported';

interface UsePushSubscriptionResult {
  supported: boolean;
  permission: PermissionState;
  subscription: PushSubscription | null;
  loading: boolean;
  error: string | null;
  requestPermission: () => Promise<PermissionState>;
  subscribe: () => Promise<PushSubscription | null>;
  unsubscribe: () => Promise<void>;
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
  return out;
}

function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

async function getRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null;
  return (
    (await navigator.serviceWorker.getRegistration()) ??
    (await navigator.serviceWorker.ready)
  );
}

async function fetchVapidKey(): Promise<string> {
  const envKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (envKey) return envKey;
  const resp = await api.get<{ key: string }>('/api/push/vapid-public-key');
  return resp.key;
}

export function usePushSubscription(): UsePushSubscriptionResult {
  const [supported, setSupported] = useState(false);
  const [permission, setPermission] = useState<PermissionState>('default');
  const [subscription, setSubscription] = useState<PushSubscription | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initial state on mount.
  useEffect(() => {
    if (!isPushSupported()) {
      setSupported(false);
      setPermission('unsupported');
      return;
    }
    setSupported(true);
    setPermission(Notification.permission as PermissionState);

    let cancelled = false;
    (async () => {
      try {
        const reg = await getRegistration();
        if (!reg || cancelled) return;
        const sub = await reg.pushManager.getSubscription();
        if (cancelled) return;
        setSubscription(sub);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load subscription');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const requestPermission = useCallback(async (): Promise<PermissionState> => {
    if (!isPushSupported()) return 'unsupported';
    const next = await Notification.requestPermission();
    setPermission(next as PermissionState);
    return next as PermissionState;
  }, []);

  const subscribe = useCallback(async (): Promise<PushSubscription | null> => {
    if (!isPushSupported()) return null;
    setLoading(true);
    setError(null);
    try {
      const reg = await getRegistration();
      if (!reg) throw new Error('Service worker not ready');

      // Make sure the user has granted permission first.
      let perm = Notification.permission as PermissionState;
      if (perm !== 'granted') {
        perm = await requestPermission();
      }
      if (perm !== 'granted') {
        throw new Error(perm === 'denied' ? 'permission-denied' : 'permission-not-granted');
      }

      const vapidKey = await fetchVapidKey();
      const existing = await reg.pushManager.getSubscription();
      const sub =
        existing ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidKey).buffer as ArrayBuffer,
        }));

      const json = sub.toJSON() as {
        endpoint?: string;
        keys?: { p256dh?: string; auth?: string };
      };
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        throw new Error('Push subscription missing required keys');
      }

      await api.post('/api/push/subscribe', {
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
        userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
      });

      await setCachedPushSubscription({
        id: 'self',
        endpoint: json.endpoint,
        p256dh: json.keys.p256dh,
        auth: json.keys.auth,
        createdAt: Date.now(),
      });

      setSubscription(sub);
      return sub;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to subscribe';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [requestPermission]);

  const unsubscribe = useCallback(async (): Promise<void> => {
    if (!isPushSupported()) return;
    setLoading(true);
    setError(null);
    try {
      const reg = await getRegistration();
      if (!reg) return;
      const sub = await reg.pushManager.getSubscription();
      if (!sub) return;

      const cached = await getCachedPushSubscription();
      const endpoint = sub.endpoint || cached?.endpoint;
      if (endpoint) {
        try {
          await api.post('/api/push/unsubscribe', { endpoint });
        } catch {
          // Best-effort: still unsubscribe locally even if server delete failed.
        }
      }
      await sub.unsubscribe();
      await clearCachedPushSubscription();
      setSubscription(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unsubscribe');
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    supported,
    permission,
    subscription,
    loading,
    error,
    requestPermission,
    subscribe,
    unsubscribe,
  };
}
