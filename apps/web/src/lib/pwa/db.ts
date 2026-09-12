'use client';

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { ChatMessage } from '@/components/chat/message-bubble';

const DB_NAME = 'replica-pwa';
// v2: `messages` gained an `by-owner` index and the store is wiped on upgrade —
// v1 read every cached message regardless of which owner it belonged to,
// leaking chat history between different owners signed into the same browser.
const DB_VERSION = 2;

export interface CachedChatMessage extends Omit<ChatMessage, 'timestamp'> {
  threadId?: string;
  ownerId: string;
  timestamp: number; // store as epoch ms for indexing
}

export interface QueuedMessage {
  id: string;
  ownerId: string;
  threadId?: string;
  text: string;
  createdAt: number;
  attempts: number;
}

export interface CachedKnowledgeEntry {
  entry_id: string;
  ownerId: string;
  text: string;
  source?: string;
  tags?: string[];
  content_type?: string;
  language?: string;
  updated_at: number;
}

export interface CachedPushSubscription {
  id: 'self';
  endpoint: string;
  p256dh: string;
  auth: string;
  createdAt: number;
}

interface ReplicaDb extends DBSchema {
  messages: {
    key: string;
    value: CachedChatMessage;
    indexes: {
      'by-thread': string;
      'by-timestamp': number;
      'by-owner': string;
    };
  };
  'queued-messages': {
    key: string;
    value: QueuedMessage;
  };
  'knowledge-entries': {
    key: string;
    value: CachedKnowledgeEntry;
    indexes: {
      'by-updated': number;
    };
  };
  'push-subscription': {
    key: string;
    value: CachedPushSubscription;
  };
}

let dbPromise: Promise<IDBPDatabase<ReplicaDb>> | null = null;

function getDb(): Promise<IDBPDatabase<ReplicaDb>> {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('IndexedDB is only available in the browser'));
  }
  if (!dbPromise) {
    dbPromise = openDB<ReplicaDb>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion) {
        // v1 cached messages from every owner in one unscoped store. Rather
        // than try to backfill ownership on old rows, drop and recreate it —
        // it's a cache; the server remains the source of truth.
        if (oldVersion < 2 && db.objectStoreNames.contains('messages')) {
          db.deleteObjectStore('messages');
        }
        if (!db.objectStoreNames.contains('messages')) {
          const store = db.createObjectStore('messages', { keyPath: 'id' });
          store.createIndex('by-thread', 'threadId');
          store.createIndex('by-timestamp', 'timestamp');
          store.createIndex('by-owner', 'ownerId');
        }
        if (!db.objectStoreNames.contains('queued-messages')) {
          db.createObjectStore('queued-messages', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('knowledge-entries')) {
          const store = db.createObjectStore('knowledge-entries', { keyPath: 'entry_id' });
          store.createIndex('by-updated', 'updated_at');
        }
        if (!db.objectStoreNames.contains('push-subscription')) {
          db.createObjectStore('push-subscription', { keyPath: 'id' });
        }
      },
      blocking() {
        // Another tab is waiting to upgrade (e.g. after a deploy bumped
        // DB_VERSION). Close our connection so it isn't stuck waiting on us.
        dbPromise?.then((db) => db.close());
        dbPromise = null;
      },
    });
  }
  return dbPromise;
}

// ── Messages ─────────────────────────────────────────────────────────────

export async function getMessages(ownerId: string, threadId?: string): Promise<ChatMessage[]> {
  if (!ownerId) return [];
  try {
    const db = await getDb();
    const candidates = threadId
      ? await db.getAllFromIndex('messages', 'by-thread', threadId)
      : await db.getAllFromIndex('messages', 'by-owner', ownerId);
    return candidates
      .filter((m) => m.ownerId === ownerId)
      .sort((a, b) => a.timestamp - b.timestamp)
      .map(({ ownerId: _ownerId, threadId: _threadId, timestamp, ...rest }) => ({
        ...rest,
        timestamp: new Date(timestamp),
      }));
  } catch {
    return [];
  }
}

export async function appendMessage(
  message: ChatMessage,
  ownerId: string,
  threadId?: string,
): Promise<void> {
  try {
    const db = await getDb();
    const cached: CachedChatMessage = {
      ...message,
      timestamp:
        message.timestamp instanceof Date
          ? message.timestamp.getTime()
          : Date.now(),
      ownerId,
      threadId,
    };
    await db.put('messages', cached);
  } catch {
    /* ignore */
  }
}

export async function trimThreadMessages(threadId: string, max = 100): Promise<void> {
  try {
    const db = await getDb();
    const tx = db.transaction('messages', 'readwrite');
    const all = await tx.store.index('by-thread').getAll(threadId);
    if (all.length <= max) {
      await tx.done;
      return;
    }
    const sorted = all.sort((a, b) => a.timestamp - b.timestamp);
    const toDelete = sorted.slice(0, sorted.length - max);
    for (const m of toDelete) {
      await tx.store.delete(m.id);
    }
    await tx.done;
  } catch {
    /* ignore */
  }
}

export async function deleteMessage(id: string): Promise<void> {
  try {
    const db = await getDb();
    await db.delete('messages', id);
  } catch {
    /* ignore */
  }
}

// ── Queued messages ─────────────────────────────────────────────────────

export async function enqueueMessage(q: QueuedMessage): Promise<void> {
  const db = await getDb();
  await db.put('queued-messages', q);
}

export async function dequeueMessage(id: string): Promise<void> {
  const db = await getDb();
  await db.delete('queued-messages', id);
}

export async function listQueuedMessages(): Promise<QueuedMessage[]> {
  try {
    const db = await getDb();
    const all = await db.getAll('queued-messages');
    return all.sort((a, b) => a.createdAt - b.createdAt);
  } catch {
    return [];
  }
}

export async function updateQueuedAttempts(id: string, attempts: number): Promise<void> {
  try {
    const db = await getDb();
    const item = await db.get('queued-messages', id);
    if (item) {
      item.attempts = attempts;
      await db.put('queued-messages', item);
    }
  } catch {
    /* ignore */
  }
}

// ── Knowledge entries ────────────────────────────────────────────────────

export async function cacheKnowledgeEntry(entry: CachedKnowledgeEntry): Promise<void> {
  try {
    const db = await getDb();
    await db.put('knowledge-entries', entry);
  } catch {
    /* ignore */
  }
}

export async function searchKnowledgeCached(query: string): Promise<CachedKnowledgeEntry[]> {
  try {
    const db = await getDb();
    const all = await db.getAll('knowledge-entries');
    if (!query.trim()) return all.sort((a, b) => b.updated_at - a.updated_at);
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    return all
      .filter((entry) => {
        const haystack = [
          entry.text ?? '',
          entry.source ?? '',
          (entry.tags ?? []).join(' '),
        ]
          .join(' ')
          .toLowerCase();
        return tokens.every((tok) => haystack.includes(tok));
      })
      .sort((a, b) => b.updated_at - a.updated_at);
  } catch {
    return [];
  }
}

// ── Push subscription ────────────────────────────────────────────────────

export async function getCachedPushSubscription(): Promise<CachedPushSubscription | undefined> {
  try {
    const db = await getDb();
    return await db.get('push-subscription', 'self');
  } catch {
    return undefined;
  }
}

export async function setCachedPushSubscription(sub: CachedPushSubscription): Promise<void> {
  try {
    const db = await getDb();
    await db.put('push-subscription', sub);
  } catch {
    /* ignore */
  }
}

export async function clearCachedPushSubscription(): Promise<void> {
  try {
    const db = await getDb();
    await db.delete('push-subscription', 'self');
  } catch {
    /* ignore */
  }
}
