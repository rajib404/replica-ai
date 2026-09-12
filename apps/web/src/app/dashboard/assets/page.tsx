'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  LayoutGrid,
  List,
  RefreshCw,
  X,
  Search,
  Sparkles,
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  type KnowledgeEntry,
  type AssetCategory,
  classify,
  displayName,
  formatDate,
  CATEGORY_META,
  CATEGORY_ORDER,
  PreviewModal,
  AssetRow,
  CategorySection,
} from '@/components/assets/shared';

// ─── Types ────────────────────────────────────────────────────────────────────

interface KnowledgeListResponse {
  entries: KnowledgeEntry[];
  total: number;
  page: number;
  page_size: number;
}

interface SearchHit {
  entry_id: string;
  content_type: string;
  score: number;
  content_preview: string | null;
  chunk_index?: number;
}

interface SearchResponse {
  query: string;
  results: SearchHit[];
  total: number;
}

type ViewMode = 'category' | 'list';

// ─── Search result row (owner-only AI search) ────────────────────────────────

function SearchResultRow({
  entry,
  preview,
  score,
  onOpen,
}: {
  entry: KnowledgeEntry;
  preview: string | null;
  score: number;
  onOpen: () => void;
}) {
  const cat = classify(entry);
  const meta = CATEGORY_META[cat];
  const Icon = meta.icon;
  const name = displayName(entry);
  const pct = Math.round(score * 100);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-start gap-3 rounded-xl border bg-card px-4 py-3 text-left text-sm transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className={cn('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
        <Icon className={cn('h-4 w-4', meta.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{name}</p>
        {preview && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{preview}</p>
        )}
        <div className="mt-1.5 flex items-center gap-2">
          <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', meta.bg, meta.color)}>
            {meta.label}
          </span>
          <span className="text-[10px] text-muted-foreground">{formatDate(entry.created_at)}</span>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1 pl-2">
        <span className="text-xs font-semibold text-primary">{pct}%</span>
        <div className="h-1 w-12 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </button>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AssetsPage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>('category');
  const [activeFilter, setActiveFilter] = useState<AssetCategory | 'all'>('all');
  const [preview, setPreview] = useState<KnowledgeEntry | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchHits, setSearchHits] = useState<SearchHit[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<KnowledgeListResponse>('/api/knowledge/entries?page_size=200');
      setEntries(resp.entries ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load assets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Debounced semantic search
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!searchQuery.trim()) { setSearchHits([]); return; }

    searchDebounceRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const resp = await api.post<SearchResponse>('/api/search', {
          query: searchQuery.trim(),
          top_k: 20,
        });
        setSearchHits(resp.results ?? []);
      } catch {
        setSearchHits([]);
      } finally {
        setSearchLoading(false);
      }
    }, 350);

    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [searchQuery]);

  // Map search hits → full entries, deduplicated (best-score chunk per entry)
  const searchResults = useMemo(() => {
    const byId = new Map(entries.map((e) => [e.id, e]));
    const seen = new Set<string>();
    return searchHits
      .map((h) => ({ entry: byId.get(h.entry_id), hit: h }))
      .filter((r): r is { entry: KnowledgeEntry; hit: SearchHit } => {
        if (!r.entry || seen.has(r.hit.entry_id)) return false;
        seen.add(r.hit.entry_id);
        return true;
      });
  }, [searchHits, entries]);

  const isSearchActive = searchQuery.trim().length > 0;

  const grouped = useMemo(() => {
    const map = new Map<AssetCategory, KnowledgeEntry[]>(
      CATEGORY_ORDER.map((c) => [c, []])
    );
    for (const e of entries) map.get(classify(e))!.push(e);
    return map;
  }, [entries]);

  const counts = useMemo(() => {
    const c: Partial<Record<AssetCategory, number>> = {};
    for (const e of entries) {
      const cat = classify(e);
      c[cat] = (c[cat] ?? 0) + 1;
    }
    return c;
  }, [entries]);

  const chronological = useMemo(() => {
    const list =
      activeFilter === 'all'
        ? [...entries]
        : entries.filter((e) => classify(e) === activeFilter);
    return list.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  }, [entries, activeFilter]);

  if (!loading && entries.length === 0 && !error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Archive className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">Assets</h1>
        <p className="max-w-md text-center text-muted-foreground">
          Upload documents, audio, and video from the mobile app or via the API. Everything
          you share will appear here, organised by type.
        </p>
      </div>
    );
  }

  return (
    <>
      {preview && <PreviewModal entry={preview} onClose={() => setPreview(null)} />}

      <div className="flex h-full flex-col">
        {/* Header */}
        <div className="flex flex-col gap-4 border-b px-4 pb-4 pt-5 md:px-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                <Archive className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-bold">Assets</h1>
                <p className="text-xs text-muted-foreground">
                  {loading ? 'Loading…' : `${entries.length} ${entries.length === 1 ? 'item' : 'items'}`}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={load}
                disabled={loading}
                className="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-accent disabled:opacity-50"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
                <span className="hidden sm:inline">Refresh</span>
              </button>
              <div className="flex rounded-md border">
                <button
                  type="button"
                  onClick={() => setView('category')}
                  className={cn(
                    'flex items-center gap-1.5 rounded-l-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                    view === 'category'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                  )}
                >
                  <LayoutGrid className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Categories</span>
                </button>
                <button
                  type="button"
                  onClick={() => setView('list')}
                  className={cn(
                    'flex items-center gap-1.5 rounded-r-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                    view === 'list'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                  )}
                >
                  <List className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">List</span>
                </button>
              </div>
            </div>
          </div>

          {/* AI Search bar */}
          {!loading && entries.length > 0 && (
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
                {searchLoading
                  ? <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
                  : <Search className="h-4 w-4 text-muted-foreground" />}
              </div>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="AI search — describe what you're looking for…"
                className="h-9 w-full rounded-lg border bg-background pl-9 pr-9 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute inset-y-0 right-2 flex items-center p-1 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Category filter pills — list view (hidden when searching) */}
          {view === 'list' && !loading && entries.length > 0 && !isSearchActive && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setActiveFilter('all')}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  activeFilter === 'all'
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'hover:bg-accent',
                )}
              >
                All ({entries.length})
              </button>
              {CATEGORY_ORDER.map((cat) => {
                const count = counts[cat] ?? 0;
                if (count === 0) return null;
                const meta = CATEGORY_META[cat];
                const Icon = meta.icon;
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setActiveFilter(cat)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                      activeFilter === cat
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'hover:bg-accent',
                    )}
                  >
                    <Icon className="h-3 w-3" />
                    {meta.label} ({count})
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-4 md:px-6">
          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {/* Search results */}
          {!loading && !error && isSearchActive && (
            <div className="space-y-3">
              {searchLoading && searchResults.length === 0 && (
                <div className="flex items-center justify-center py-16">
                  <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}

              {!searchLoading && searchResults.length === 0 && (
                <div className="flex flex-col items-center gap-3 py-16 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
                    <Sparkles className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">No matching assets found</p>
                  <p className="max-w-xs text-xs text-muted-foreground">
                    Try describing the content differently — the AI search looks for meaning, not just keywords.
                  </p>
                </div>
              )}

              {searchResults.length > 0 && (
                <>
                  <div className="flex items-center gap-2 pb-1">
                    <Sparkles className="h-3.5 w-3.5 text-primary" />
                    <p className="text-xs text-muted-foreground">
                      {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} for &ldquo;{searchQuery}&rdquo;
                    </p>
                  </div>
                  {searchResults.map(({ entry, hit }) => (
                    <SearchResultRow
                      key={hit.entry_id}
                      entry={entry}
                      preview={hit.content_preview}
                      score={hit.score}
                      onOpen={() => setPreview(entry)}
                    />
                  ))}
                </>
              )}
            </div>
          )}

          {!loading && !error && !isSearchActive && view === 'category' && (
            <div className="space-y-8">
              {CATEGORY_ORDER.map((cat) => (
                <CategorySection
                  key={cat}
                  cat={cat}
                  items={grouped.get(cat) ?? []}
                  onOpen={setPreview}
                />
              ))}
            </div>
          )}

          {!loading && !error && !isSearchActive && view === 'list' && (
            <div className="space-y-2">
              {chronological.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">No items here.</p>
              ) : (
                chronological.map((e) => (
                  <AssetRow key={e.id} entry={e} onOpen={() => setPreview(e)} />
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
