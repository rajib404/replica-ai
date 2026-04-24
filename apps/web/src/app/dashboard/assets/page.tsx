'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Archive,
  FileText,
  Image,
  Mic,
  Video,
  MessageSquare,
  File,
  LayoutGrid,
  List,
  RefreshCw,
  Calendar,
  Tag,
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

// ─── Types ────────────────────────────────────────────────────────────────────

interface KnowledgeEntry {
  entry_id: string;
  text: string;
  source?: string;
  tags?: string[];
  content_type?: string;
  language?: string;
  updated_at?: string;
}

type AssetCategory = 'document' | 'image' | 'audio' | 'video' | 'voice' | 'conversation' | 'other';
type ViewMode = 'category' | 'list';

// ─── Classifier ───────────────────────────────────────────────────────────────

function classify(entry: KnowledgeEntry): AssetCategory {
  const ct = (entry.content_type ?? '').toLowerCase();
  const src = (entry.source ?? '').toLowerCase();
  const tags = (entry.tags ?? []).map((t) => t.toLowerCase());

  if (tags.includes('conversation') || ct === 'conversation') return 'conversation';
  if (tags.includes('voice') || tags.includes('voice_note') || ct === 'voice')
    return 'voice';

  if (ct.startsWith('image/') || /\.(jpg|jpeg|png|gif|webp|avif|svg|heic)$/i.test(src))
    return 'image';
  if (ct.startsWith('video/') || /\.(mp4|mov|avi|webm|mkv|m4v)$/i.test(src))
    return 'video';
  if (
    ct.startsWith('audio/') ||
    /\.(mp3|m4a|wav|ogg|flac|aac|opus)$/i.test(src)
  )
    return 'audio';
  if (
    ct === 'application/pdf' ||
    ct.includes('word') ||
    ct.includes('document') ||
    ct.startsWith('text/') ||
    /\.(pdf|doc|docx|txt|md|rtf|odt|csv|json|xml)$/i.test(src)
  )
    return 'document';

  return 'other';
}

// ─── Category metadata ────────────────────────────────────────────────────────

const CATEGORIES: {
  id: AssetCategory;
  label: string;
  icon: React.ElementType;
  color: string;
  bg: string;
}[] = [
  {
    id: 'document',
    label: 'Documents',
    icon: FileText,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
  },
  {
    id: 'image',
    label: 'Images',
    icon: Image,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
  },
  {
    id: 'audio',
    label: 'Audio',
    icon: Mic,
    color: 'text-violet-500',
    bg: 'bg-violet-500/10',
  },
  {
    id: 'video',
    label: 'Video',
    icon: Video,
    color: 'text-rose-500',
    bg: 'bg-rose-500/10',
  },
  {
    id: 'voice',
    label: 'Voice Notes',
    icon: Mic,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
  },
  {
    id: 'conversation',
    label: 'Conversations',
    icon: MessageSquare,
    color: 'text-indigo-500',
    bg: 'bg-indigo-500/10',
  },
  {
    id: 'other',
    label: 'Other',
    icon: File,
    color: 'text-muted-foreground',
    bg: 'bg-muted',
  },
];

function getCategoryMeta(id: AssetCategory) {
  return CATEGORIES.find((c) => c.id === id) ?? CATEGORIES[CATEGORIES.length - 1];
}

function formatDate(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AssetCard({ entry }: { entry: KnowledgeEntry }) {
  const cat = classify(entry);
  const meta = getCategoryMeta(cat);
  const Icon = meta.icon;

  return (
    <article className="group flex flex-col gap-2 rounded-xl border bg-card p-4 text-sm transition-colors hover:bg-accent/40">
      <div className="flex items-start justify-between gap-2">
        <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
          <Icon className={cn('h-4 w-4', meta.color)} />
        </div>
        <Badge variant="secondary" className="shrink-0 text-[10px] capitalize">
          {meta.label}
        </Badge>
      </div>
      {entry.source && (
        <p className="truncate font-medium leading-tight" title={entry.source}>
          {entry.source.split('/').pop() ?? entry.source}
        </p>
      )}
      <p className="line-clamp-2 text-xs text-muted-foreground">{entry.text}</p>
      {entry.updated_at && (
        <div className="mt-auto flex items-center gap-1 text-[10px] text-muted-foreground">
          <Calendar className="h-3 w-3" />
          {formatDate(entry.updated_at)}
        </div>
      )}
      {entry.tags && entry.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {entry.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
              {tag}
            </span>
          ))}
          {entry.tags.length > 3 && (
            <span className="text-[10px] text-muted-foreground">+{entry.tags.length - 3}</span>
          )}
        </div>
      )}
    </article>
  );
}

function AssetRow({ entry }: { entry: KnowledgeEntry }) {
  const cat = classify(entry);
  const meta = getCategoryMeta(cat);
  const Icon = meta.icon;

  return (
    <article className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3 text-sm transition-colors hover:bg-accent/40">
      <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
        <Icon className={cn('h-4 w-4', meta.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          {entry.source ? (entry.source.split('/').pop() ?? entry.source) : entry.text.slice(0, 60)}
        </p>
        <p className="truncate text-xs text-muted-foreground">{entry.text.slice(0, 100)}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {entry.tags && entry.tags.length > 0 && (
          <div className="hidden items-center gap-1 sm:flex">
            <Tag className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{entry.tags[0]}</span>
          </div>
        )}
        <Badge variant="secondary" className="text-[10px] capitalize">
          {meta.label}
        </Badge>
        {entry.updated_at && (
          <span className="hidden w-24 text-right text-xs text-muted-foreground sm:block">
            {formatDate(entry.updated_at)}
          </span>
        )}
      </div>
    </article>
  );
}

// ─── Category section (used in category view) ─────────────────────────────────

function CategorySection({
  category,
  entries,
}: {
  category: (typeof CATEGORIES)[number];
  entries: KnowledgeEntry[];
}) {
  const [expanded, setExpanded] = useState(true);
  const Icon = category.icon;

  if (entries.length === 0) return null;

  return (
    <section>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mb-3 flex w-full items-center gap-2 text-left"
      >
        <div className={cn('flex h-7 w-7 items-center justify-center rounded-lg', category.bg)}>
          <Icon className={cn('h-3.5 w-3.5', category.color)} />
        </div>
        <span className="font-semibold">{category.label}</span>
        <Badge variant="secondary" className="ml-1">
          {entries.length}
        </Badge>
        <span className="ml-auto text-xs text-muted-foreground">{expanded ? 'Collapse' : 'Expand'}</span>
      </button>
      {expanded && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {entries.map((e) => (
            <AssetCard key={e.entry_id} entry={e} />
          ))}
        </div>
      )}
    </section>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AssetsPage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>('category');
  const [activeFilter, setActiveFilter] = useState<AssetCategory | 'all'>('all');

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<{ entries: KnowledgeEntry[] }>('/api/knowledge/entries');
      setEntries(resp.entries ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load assets');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Group entries by category
  const grouped = useMemo(() => {
    const map = new Map<AssetCategory, KnowledgeEntry[]>();
    for (const cat of CATEGORIES) map.set(cat.id, []);
    for (const entry of entries) {
      const cat = classify(entry);
      map.get(cat)!.push(entry);
    }
    return map;
  }, [entries]);

  // Chronological list, optionally filtered
  const chronological = useMemo(() => {
    const list = activeFilter === 'all' ? [...entries] : entries.filter((e) => classify(e) === activeFilter);
    return list.sort((a, b) => {
      const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return tb - ta;
    });
  }, [entries, activeFilter]);

  const totalByCategory = useMemo(() => {
    const counts: Partial<Record<AssetCategory, number>> = {};
    for (const entry of entries) {
      const cat = classify(entry);
      counts[cat] = (counts[cat] ?? 0) + 1;
    }
    return counts;
  }, [entries]);

  // ── Empty state ──
  if (!loading && entries.length === 0 && !error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Archive className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">Assets</h1>
        <p className="max-w-md text-center text-muted-foreground">
          Upload documents, photos, audio, video, and voice notes. Everything you share will appear
          here, automatically organised by type.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ── */}
      <div className="flex flex-col gap-4 border-b px-4 pb-4 pt-5 md:px-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <Archive className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold">Assets</h1>
              <p className="text-xs text-muted-foreground">
                {entries.length} {entries.length === 1 ? 'item' : 'items'} across{' '}
                {Object.keys(totalByCategory).length} {Object.keys(totalByCategory).length === 1 ? 'category' : 'categories'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={load}
              disabled={loading}
              className="gap-1.5"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            {/* View toggle */}
            <div className="flex rounded-md border">
              <button
                type="button"
                onClick={() => setView('category')}
                className={cn(
                  'flex items-center gap-1.5 rounded-l-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                  view === 'category'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
                title="Category view"
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
                    : 'text-muted-foreground hover:text-foreground',
                )}
                title="List view"
              >
                <List className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">List</span>
              </button>
            </div>
          </div>
        </div>

        {/* Category filter pills (list view only) */}
        {view === 'list' && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveFilter('all')}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                activeFilter === 'all'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'hover:bg-accent',
              )}
            >
              All ({entries.length})
            </button>
            {CATEGORIES.map((cat) => {
              const count = totalByCategory[cat.id] ?? 0;
              if (count === 0) return null;
              const Icon = cat.icon;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setActiveFilter(cat.id)}
                  className={cn(
                    'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                    activeFilter === cat.id
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'hover:bg-accent',
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {cat.label} ({count})
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Content ── */}
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
            {CATEGORIES.map((cat) => (
              <CategorySection
                key={cat.id}
                category={cat}
                entries={grouped.get(cat.id) ?? []}
              />
            ))}
          </div>
        )}

        {!loading && !error && view === 'list' && (
          <div className="space-y-2">
            {chronological.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No items in this category.</p>
            ) : (
              chronological.map((e) => <AssetRow key={e.entry_id} entry={e} />)
            )}
          </div>
        )}
      </div>
    </div>
  );
}
