'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  FileText,
  ImageIcon,
  Mic,
  Video,
  AlignLeft,
  File,
  LayoutGrid,
  List,
  RefreshCw,
  Calendar,
  ChevronDown,
  ChevronRight,
  X,
  Download,
  Play,
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface KnowledgeEntry {
  id: string;
  owner_id: string;
  content_type: 'text' | 'audio' | 'video' | 'document';
  original_content_path: string | null;
  original_language: string | null;
  english_translation: string | null;
  embedding_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

interface KnowledgeListResponse {
  entries: KnowledgeEntry[];
  total: number;
  page: number;
  page_size: number;
}

type AssetCategory = 'document' | 'audio' | 'video' | 'text';
type ViewMode = 'category' | 'list';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function classify(entry: KnowledgeEntry): AssetCategory {
  return (entry.content_type as AssetCategory) ?? 'text';
}

/** Best display name for an entry. */
function displayName(entry: KnowledgeEntry): string {
  // metadata.filename is the original upload filename
  const metaFile = entry.metadata?.filename as string | undefined;
  if (metaFile) return metaFile;
  if (entry.original_content_path) {
    return entry.original_content_path.split('/').pop() ?? entry.original_content_path;
  }
  // For English text entries, english_translation is null; content lives in metadata.original_text
  const preview = entry.english_translation
    ?? (entry.metadata?.original_text as string | undefined)
    ?? '';
  return preview.slice(0, 60) + (preview.length > 60 ? '…' : '') || `Entry ${entry.id.slice(0, 8)}`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

const CATEGORY_META: Record<
  AssetCategory,
  { label: string; icon: React.ElementType; color: string; bg: string }
> = {
  document: { label: 'Documents', icon: FileText,  color: 'text-blue-500',    bg: 'bg-blue-500/10' },
  audio:    { label: 'Audio',     icon: Mic,        color: 'text-violet-500',  bg: 'bg-violet-500/10' },
  video:    { label: 'Video',     icon: Video,      color: 'text-rose-500',    bg: 'bg-rose-500/10' },
  text:     { label: 'Notes',     icon: AlignLeft,  color: 'text-amber-500',   bg: 'bg-amber-500/10' },
};

const CATEGORY_ORDER: AssetCategory[] = ['document', 'audio', 'video', 'text'];

// ─── File preview hook ────────────────────────────────────────────────────────

const API_BASE =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000')
    : '';

function useFileBlobUrl(entryId: string | null) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!entryId) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    setBlobUrl(null);

    const token = localStorage.getItem('access_token');
    fetch(`${API_BASE}/api/knowledge/entries/${entryId}/file`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (cancelled || !blob) { if (!cancelled) setError(true); return; }
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        setBlobUrl(url);
      })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => {
      cancelled = true;
      if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
    };
  }, [entryId]);

  return { blobUrl, loading, error };
}

// ─── Preview modal ────────────────────────────────────────────────────────────

function PreviewModal({ entry, onClose }: { entry: KnowledgeEntry; onClose: () => void }) {
  const cat = classify(entry);
  const hasFile = !!entry.original_content_path;
  const { blobUrl, loading, error } = useFileBlobUrl(hasFile ? entry.id : null);
  const name = displayName(entry);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative flex w-full max-w-3xl flex-col rounded-2xl bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 border-b px-4 py-3">
          <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', CATEGORY_META[cat].bg)}>
            {(() => { const Icon = CATEGORY_META[cat].icon; return <Icon className={cn('h-4 w-4', CATEGORY_META[cat].color)} />; })()}
          </div>
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{name}</p>
          <div className="flex shrink-0 items-center gap-2">
            {blobUrl && (
              <a
                href={blobUrl}
                download={name}
                className="rounded-md border px-2 py-1 text-xs hover:bg-accent"
              >
                <Download className="h-3.5 w-3.5" />
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 hover:bg-accent"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex min-h-48 flex-col items-center justify-center overflow-auto p-4">
          {loading && <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />}

          {error && (
            <p className="text-sm text-muted-foreground">
              {hasFile ? 'Could not load file.' : 'No file attached to this entry.'}
            </p>
          )}

          {blobUrl && cat === 'document' && (
            <iframe
              src={blobUrl}
              title={name}
              className="h-[70vh] w-full rounded-lg border"
            />
          )}

          {blobUrl && cat === 'audio' && (
            <div className="flex w-full flex-col items-center gap-4 py-6">
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-violet-500/10">
                <Mic className="h-10 w-10 text-violet-500" />
              </div>
              <audio controls src={blobUrl} className="w-full max-w-sm" />
            </div>
          )}

          {blobUrl && cat === 'video' && (
            <video
              controls
              src={blobUrl}
              className="max-h-[70vh] w-full rounded-lg"
            />
          )}

          {/* Text entries: show full translation */}
          {!hasFile && cat === 'text' && entry.english_translation && (
            <div className="h-80 w-full overflow-y-auto rounded-lg border bg-muted/30 p-4">
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{entry.english_translation}</p>
            </div>
          )}
        </div>

        {/* Footer meta */}
        <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-muted-foreground">
          <span className={cn('capitalize font-medium', CATEGORY_META[cat].color)}>
            {CATEGORY_META[cat].label}
          </span>
          <span>{formatDate(entry.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

// ─── Asset card (category grid view) ─────────────────────────────────────────

function AssetCard({ entry, onOpen }: { entry: KnowledgeEntry; onOpen: () => void }) {
  const cat = classify(entry);
  const meta = CATEGORY_META[cat];
  const Icon = meta.icon;
  const name = displayName(entry);
  const hasFile = !!entry.original_content_path;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex w-full flex-col gap-2 rounded-xl border bg-card p-4 text-left text-sm transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start justify-between gap-2">
        <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
          <Icon className={cn('h-4 w-4', meta.color)} />
        </div>
        {hasFile && (
          <Play className="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        )}
      </div>

      <p className="truncate font-medium leading-tight" title={name}>{name}</p>

      {entry.english_translation && (
        <p className="line-clamp-2 text-xs text-muted-foreground">{entry.english_translation}</p>
      )}

      <div className="mt-auto flex items-center gap-1 text-[10px] text-muted-foreground">
        <Calendar className="h-3 w-3" />
        {formatDate(entry.created_at)}
      </div>
    </button>
  );
}

// ─── Asset row (list view) ────────────────────────────────────────────────────

function AssetRow({ entry, onOpen }: { entry: KnowledgeEntry; onOpen: () => void }) {
  const cat = classify(entry);
  const meta = CATEGORY_META[cat];
  const Icon = meta.icon;
  const name = displayName(entry);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-lg border bg-card px-4 py-3 text-left text-sm transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
        <Icon className={cn('h-4 w-4', meta.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{name}</p>
        {entry.english_translation && (
          <p className="truncate text-xs text-muted-foreground">{entry.english_translation}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className={cn('hidden rounded-full px-2 py-0.5 text-[10px] font-medium sm:inline', meta.bg, meta.color)}>
          {meta.label}
        </span>
        <span className="hidden w-24 text-right text-xs text-muted-foreground sm:block">
          {formatDate(entry.created_at)}
        </span>
      </div>
    </button>
  );
}

// ─── Category section ─────────────────────────────────────────────────────────

function CategorySection({
  cat,
  items,
  onOpen,
}: {
  cat: AssetCategory;
  items: KnowledgeEntry[];
  onOpen: (e: KnowledgeEntry) => void;
}) {
  const [open, setOpen] = useState(true);
  const meta = CATEGORY_META[cat];
  const Icon = meta.icon;
  if (items.length === 0) return null;

  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mb-3 flex w-full items-center gap-2 text-left"
      >
        <div className={cn('flex h-7 w-7 items-center justify-center rounded-lg', meta.bg)}>
          <Icon className={cn('h-3.5 w-3.5', meta.color)} />
        </div>
        <span className="font-semibold">{meta.label}</span>
        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', meta.bg, meta.color)}>
          {items.length}
        </span>
        <span className="ml-auto text-muted-foreground">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((e) => <AssetCard key={e.id} entry={e} onOpen={() => onOpen(e)} />)}
        </div>
      )}
    </section>
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

          {/* Category filter pills — list view */}
          {view === 'list' && !loading && entries.length > 0 && (
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

          {!loading && !error && view === 'category' && (
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

          {!loading && !error && view === 'list' && (
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
