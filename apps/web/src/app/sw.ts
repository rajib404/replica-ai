/// <reference lib="webworker" />
/* eslint-disable */

import { defaultCache } from '@serwist/next/worker';
import type { PrecacheEntry, SerwistGlobalConfig } from 'serwist';
import {
  Serwist,
  CacheFirst,
  NetworkFirst,
  NetworkOnly,
  StaleWhileRevalidate,
  ExpirationPlugin,
} from 'serwist';

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope & {
  __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
};

const OFFLINE_FALLBACK_URL = '/~offline';

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  fallbacks: {
    entries: [
      {
        url: OFFLINE_FALLBACK_URL,
        matcher({ request }) {
          return request.destination === 'document';
        },
      },
    ],
  },
  runtimeCaching: [
    // HTML navigations — NetworkFirst with 3s timeout, fallback to offline page.
    {
      matcher: ({ request }) => request.mode === 'navigate',
      handler: new NetworkFirst({
        cacheName: 'html-pages',
        networkTimeoutSeconds: 3,
        plugins: [
          new ExpirationPlugin({
            maxEntries: 50,
            maxAgeSeconds: 24 * 60 * 60, // 1 day
          }),
        ],
      }),
    },
    // Static assets (JS, CSS, fonts, images) — CacheFirst with versioned cache.
    {
      matcher: ({ request }) =>
        request.destination === 'style' ||
        request.destination === 'script' ||
        request.destination === 'worker' ||
        request.destination === 'font' ||
        request.destination === 'image',
      handler: new CacheFirst({
        cacheName: 'static-assets-v1',
        plugins: [
          new ExpirationPlugin({
            maxEntries: 200,
            maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
          }),
        ],
      }),
    },
    // Knowledge entries — StaleWhileRevalidate, 24h.
    {
      matcher: ({ url }) => url.pathname.startsWith('/api/knowledge/entries'),
      handler: new StaleWhileRevalidate({
        cacheName: 'api-knowledge-entries',
        plugins: [
          new ExpirationPlugin({
            maxEntries: 50,
            maxAgeSeconds: 24 * 60 * 60,
          }),
        ],
      }),
    },
    // Health endpoint — never cache.
    {
      matcher: ({ url }) => url.pathname === '/api/health',
      handler: new NetworkOnly(),
    },
    // Default fallback to Serwist's @serwist/next defaults for everything else.
    ...defaultCache,
  ],
});

serwist.addEventListeners();

// ── Push notifications ────────────────────────────────────────────────────

self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) return;

  let payload: {
    title?: string;
    body?: string;
    url?: string;
    tag?: string;
    icon?: string;
    badge?: string;
    data?: Record<string, unknown>;
  } = {};

  try {
    payload = event.data.json();
  } catch {
    payload = { title: 'Replica AI', body: event.data.text() };
  }

  const title = payload.title ?? 'Replica AI';
  const options: NotificationOptions = {
    body: payload.body ?? '',
    icon: payload.icon ?? '/icons/icon-192.png',
    badge: payload.badge ?? '/icons/badge-72.png',
    tag: payload.tag,
    data: { url: payload.url ?? '/dashboard/chat', ...(payload.data ?? {}) },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  const data = event.notification.data as { url?: string } | undefined;
  const targetUrl = data?.url ?? '/dashboard/chat';

  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      });
      // Focus an existing window if available.
      for (const client of allClients) {
        try {
          const url = new URL(client.url);
          if (url.pathname.startsWith('/dashboard')) {
            await (client as WindowClient).focus();
            (client as WindowClient).postMessage({
              type: 'notification-click',
              url: targetUrl,
            });
            return;
          }
        } catch {
          /* ignore */
        }
      }
      await self.clients.openWindow(targetUrl);
    })(),
  );
});

// ── Background sync for queued chat messages ─────────────────────────────

self.addEventListener('sync', (event: any) => {
  if (event.tag === 'bg-sync-chat-messages') {
    event.waitUntil(
      (async () => {
        // Notify all open clients to drain their queue.
        const allClients = await self.clients.matchAll({ type: 'window' });
        for (const client of allClients) {
          client.postMessage({ type: 'flush-chat-queue' });
        }
      })(),
    );
  }
});
