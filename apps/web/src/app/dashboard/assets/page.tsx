'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
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
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

// ─── API types (matches KnowledgeEntryResponse + KnowledgeListResponse) ──────

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

// ─── Asset categories ─────────────────────────────────────────────────────────

type AssetCategory = 'document' | 'image' | 'audio' | 'video' | 'text' | 'other';
type ViewMode = 'category' | 'list';

function classify(entry: KnowledgeEntry): AssetCategory {
  const path = (entry.original_content_path ?? '').toLowerCase();
  const ct = entry.content_type;

  // Refine by file extension first
  if (/\.(jpg|jpeg|png|gif|webp|avif|svg|heic|bmp)$/i.test(path)) return 'image';
  if (/\.(mp4|mov|avi|webm|mkv|m4v)$/i.test(path)) return 'video';
  if (/\.(mp3|m4a|wav|ogg|flac|aac|opus)$/i.test(path)) return 'audio';
  if (/\.(pdf|doc|docx|odt|rtf|csv|json|xml|md)$/i.test(path)) return 'document';

  // Fall back to backend content_type
  if (ct === 'audio') return 'audio';
  if (ct === 'video') return 'video';
  if (ct === 'document') return 'document';
  if (ct === 'text') return 'text';

  return 'other';
}

const CATEGORY_META: Record<
  AssetCategory,
  { label: string; icon: React.ElementType; color: string; bg: string }
> = {
  document: { label: 'Documents', icon: FileText, color: 'text-blue-500', bg: 'bg-blue-500/10' },
  image:    { label: 'Images',    icon: ImageIcon, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  audio:    { label: 'Audio',     icon: Mic,        color: 'text-violet-500',  bg: 'bg-violet-500/10' },
  video:    { label: 'Video',     icon: Video,      color: 'text-rose-500',    bg: 'bg-rose-500/10' },
  text:     { label: 'Notes',     icon: AlignLeft,  color: 'text-amber-500',   bg: 'bg-amber-500/10' },
  other:    { label: 'Other',     icon: File,       color: 'text-muted-foreground', bg: 'bg-muted' },
};

const CATEGORY_ORDER: AssetCategory[] = ['document', 'image', 'audio', 'video', 'text', 'other'];

function filename(entry: KnowledgeEntry): string {
  if (entry.original_content_path) {
    return entry.original_content_path.split('/').pop() ?? entry.original_content_path;
  }
  const preview = entry.english_translation ?? '';
  return preview.slice(0, 48) + (preview.length > 48 ? '…' : '') || `Entry ${entry.id.slice(0, 8)}`;
}

function excerpt(entry: KnowledgeEntry, max = 100): string {
  const t = entry.english_translation ?? '';
  return t.slice(0, max) + (t.length > max ? '…' : '');
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

// ─── Card (category view) ─────────────────────────────────────────────────────

function AssetCard({ entry }: { entry: KnowledgeEntry }) {
  const cat = classify(entry);
  const meta = CATEGORY_META[cat];
  const Icon = meta.icon;
  return (
    <article className="flex flex-col gap-2 rounded-xl border bg-card p-4 text-sm transition-colors hover:bg-accent/40">
      <div className="flex items-start justify-between gap-2">
        <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
          <Icon className={cn('h-4 w-4', meta.color)} />
        </div>
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium', meta.bg, meta.color)}>
          {meta.label}
        </span>
      </div>
      <p className="truncate font-medium leading-tight" title={filename(entry)}>
        {filename(entry)}
      </p>
      {entry.english_translation && (
        <p className="line-clamp-2 text-xs text-muted-foreground">{excerpt(entry)}</p>
      )}
      <div className="mt-auto flex items-center gap-1 text-[10px] text-muted-foreground">
        <Calendar className="h-3 w-3" />
        {formatDate(entry.created_at)}
      </div>
    </article>
  );
}

// ─── Row (list view) ──────────────────────────────────────────────────────────

function AssetRow({ entry }: { entry: KnowledgeEntry }) {
  const cat = classify(entry);
  const meta = CATEGORY_META[cat];
  const Icon = meta.icon;
  return (
    <article className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3 text-sm transition-colors hover:bg-accent/40">
      <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
        <Icon className={cn('h-4 w-4', meta.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{filename(entry)}</p>
        {entry.english_translation && (
          <p className="truncate text-xs text-muted-foreground">{excerpt(entry)}</p>
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
    </article>
  );
}

// ─── Category section ─────────────────────────────────────────────────────────

function CategorySection({
  cat,
  items,
}: {
  cat: AssetCategory;
  items: KnowledgeEntry[];
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
          {items.map((e) => <AssetCard key={e.id} entry={e} />)}
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch up to 200 entries across all pages
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

  // Empty state (only when loaded + no data + no error)
  if (!loading && entries.length === 0 && !error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Archive className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">Assets</h1>
        <p className="max-w-md text-center text-muted-foreground">
          Upload documents, photos, audio, and video. Everything you share will appear here,
          automatically organised by type.
        </p>
      </div>
    );
  }

  return (
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
            {/* View toggle */}
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

        {/* Category filter pills — list view only */}
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
              <CategorySection key={cat} cat={cat} items={grouped.get(cat) ?? []} />
            ))}
          </div>
        )}

        {!loading && !error && view === 'list' && (
          <div className="space-y-2">
            {chronological.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No items here.</p>
            ) : (
              chronological.map((e) => <AssetRow key={e.id} entry={e} />)
            )}
          </div>
        )}
      </div>
    </div>
  );
}
