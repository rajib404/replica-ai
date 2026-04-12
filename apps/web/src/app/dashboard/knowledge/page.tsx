'use client';

import { useEffect, useMemo, useState } from 'react';
import { BookOpen, RefreshCw, Search, WifiOff } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { api, OfflineError } from '@/lib/api';
import { useOnlineStatus } from '@/lib/hooks/use-online-status';
import { usePullToRefresh } from '@/lib/hooks/use-pull-to-refresh';
import {
  cacheKnowledgeEntry,
  searchKnowledgeCached,
  type CachedKnowledgeEntry,
} from '@/lib/pwa/db';

interface KnowledgeEntry {
  entry_id: string;
  text: string;
  source?: string;
  tags?: string[];
  content_type?: string;
  language?: string;
  updated_at?: string;
}

interface KnowledgeListResponse {
  entries: KnowledgeEntry[];
}

export default function KnowledgePage() {
  const t = useTranslations('pwa');
  const onlineStatus = useOnlineStatus();
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [query, setQuery] = useState('');
  const [usingCache, setUsingCache] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const ptr = usePullToRefresh({
    onRefresh: async () => {
      setRefreshTick((t) => t + 1);
      // Give the load effect a tick to start, then resolve.
      await new Promise((r) => setTimeout(r, 300));
    },
  });

  useEffect(() => {
    let cancelled = false;
    const ownerId = (typeof window !== 'undefined' && localStorage.getItem('owner_id')) || '';

    async function load() {
      setError(null);
      // When offline, search the cache directly.
      if (onlineStatus === 'offline') {
        const cached = await searchKnowledgeCached(query);
        if (cancelled) return;
        setEntries(toEntries(cached));
        setUsingCache(true);
        return;
      }

      try {
        const resp = await api.get<KnowledgeListResponse>('/api/knowledge/entries');
        if (cancelled) return;
        setEntries(resp.entries ?? []);
        setUsingCache(false);
        // Cache for offline.
        for (const e of resp.entries ?? []) {
          await cacheKnowledgeEntry({
            entry_id: e.entry_id,
            ownerId,
            text: e.text,
            source: e.source,
            tags: e.tags,
            content_type: e.content_type,
            language: e.language,
            updated_at: e.updated_at ? new Date(e.updated_at).getTime() : Date.now(),
          });
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof OfflineError) {
          const cached = await searchKnowledgeCached(query);
          if (cancelled) return;
          setEntries(toEntries(cached));
          setUsingCache(true);
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load knowledge');
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [onlineStatus, query, refreshTick]);

  const filtered = useMemo(() => {
    if (!query.trim()) return entries;
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    return entries.filter((e) => {
      const hay = [e.text, e.source ?? '', (e.tags ?? []).join(' ')].join(' ').toLowerCase();
      return tokens.every((tok) => hay.includes(tok));
    });
  }, [entries, query]);

  if (entries.length === 0 && !usingCache && !error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <BookOpen className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">Knowledge Base</h1>
        <p className="max-w-md text-center text-muted-foreground">
          Upload documents, record voice notes, and add memories. Your Replica will learn from
          everything you share.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <div className="flex items-center gap-3">
        <BookOpen className="h-6 w-6" />
        <h1 className="text-xl font-bold">Knowledge Base</h1>
      </div>

      {usingCache && (
        <div className="flex items-center gap-2 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          <WifiOff className="h-3.5 w-3.5" />
          {t('offlineSearchNote')}
        </div>
      )}

      <label className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search knowledge..."
          className="h-10 w-full rounded-md border bg-background pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>

      {error && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {(ptr.isPulling || ptr.isRefreshing) && (
        <div
          className="flex items-center justify-center text-xs text-muted-foreground"
          style={{ height: Math.max(0, ptr.pullDistance) }}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${ptr.isRefreshing ? 'animate-spin' : ''}`} />
          <span className="ml-2">
            {ptr.isRefreshing ? t('refreshing') : ptr.pullDistance >= 70 ? t('releaseToRefresh') : t('pullToRefresh')}
          </span>
        </div>
      )}

      <div
        ref={ptr.bind.ref}
        className="flex-1 space-y-2 overflow-y-auto [overscroll-behavior:contain]"
      >
        {filtered.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground">No matching entries.</p>
        ) : (
          filtered.map((e) => (
            <article
              key={e.entry_id}
              className="rounded-lg border bg-card p-3 text-sm"
            >
              <p className="line-clamp-3 whitespace-pre-wrap">{e.text}</p>
              {(e.source || e.tags?.length) && (
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  {e.source && <span>{e.source}</span>}
                  {e.tags?.map((tag) => (
                    <span key={tag} className="rounded-full bg-muted px-2 py-0.5">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
      </div>
    </div>
  );
}

function toEntries(cached: CachedKnowledgeEntry[]): KnowledgeEntry[] {
  return cached.map((c) => ({
    entry_id: c.entry_id,
    text: c.text,
    source: c.source,
    tags: c.tags,
    content_type: c.content_type,
    language: c.language,
    updated_at: new Date(c.updated_at).toISOString(),
  }));
}
