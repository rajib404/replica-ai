'use client';

import {
  enqueueMessage,
  dequeueMessage,
  listQueuedMessages,
  updateQueuedAttempts,
  type QueuedMessage,
} from '@/lib/pwa/db';

const MAX_ATTEMPTS = 5;
const SYNC_TAG = 'bg-sync-chat-messages';

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `q-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

async function notifyChange(): Promise<void> {
  if (typeof window === 'undefined') return;
  const items = await listQueuedMessages();
  window.dispatchEvent(
    new CustomEvent('chat-queue-change', { detail: { count: items.length } }),
  );
}

async function requestBackgroundSync(): Promise<void> {
  if (typeof navigator === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    // Background Sync API is non-standard; gate via duck typing.
    const sync = (reg as ServiceWorkerRegistration & {
      sync?: { register: (tag: string) => Promise<void> };
    }).sync;
    if (sync && typeof sync.register === 'function') {
      await sync.register(SYNC_TAG);
    }
  } catch {
    /* ignore */
  }
}

export async function queueChatMessage(
  ownerId: string,
  text: string,
  threadId?: string,
): Promise<QueuedMessage> {
  const item: QueuedMessage = {
    id: uuid(),
    ownerId,
    text,
    threadId,
    createdAt: Date.now(),
    attempts: 0,
  };
  await enqueueMessage(item);
  await requestBackgroundSync();
  await notifyChange();
  return item;
}

export type SendFn = (msg: QueuedMessage) => Promise<void>;

export async function flushQueue(
  ownerId: string,
  send: SendFn,
): Promise<{ sent: number; failed: number }> {
  // Only flush messages queued by the currently signed-in owner — other
  // owners' queued messages stay put until they sign back in themselves.
  const items = (await listQueuedMessages()).filter((m) => m.ownerId === ownerId);
  let sent = 0;
  let failed = 0;

  for (const item of items) {
    try {
      await send(item);
      await dequeueMessage(item.id);
      sent++;
    } catch {
      const attempts = item.attempts + 1;
      if (attempts >= MAX_ATTEMPTS) {
        await dequeueMessage(item.id);
        failed++;
      } else {
        await updateQueuedAttempts(item.id, attempts);
        // Exponential backoff between sends to avoid hammering the server.
        await new Promise((r) => setTimeout(r, Math.min(2 ** attempts * 250, 4000)));
      }
    }
  }

  await notifyChange();
  return { sent, failed };
}

export async function getQueueCount(ownerId: string): Promise<number> {
  const items = await listQueuedMessages();
  return items.filter((m) => m.ownerId === ownerId).length;
}
