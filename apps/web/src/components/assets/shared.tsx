'use client';

import { useEffect, useRef, useState } from 'react';
import {
  FileText,
  ImageIcon,
  Mic,
  Video,
  AlignLeft,
  RefreshCw,
  Calendar,
  ChevronDown,
  ChevronRight,
  X,
  Download,
  Play,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface KnowledgeEntry {
  id: string;
  owner_id: string;
  content_type: 'text' | 'audio' | 'video' | 'image' | 'document';
  original_content_path: string | null;
  original_language: string | null;
  english_translation: string | null;
  embedding_id: string | null;
  category?: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export type AssetCategory = 'document' | 'audio' | 'video' | 'image' | 'text';

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function classify(entry: KnowledgeEntry): AssetCategory {
  return (entry.content_type as AssetCategory) ?? 'text';
}

/** Best display name for an entry. */
export function displayName(entry: KnowledgeEntry): string {
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

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

export const CATEGORY_META: Record<
  AssetCategory,
  { label: string; icon: React.ElementType; color: string; bg: string }
> = {
  document: { label: 'Documents', icon: FileText,   color: 'text-blue-500',    bg: 'bg-blue-500/10' },
  audio:    { label: 'Audio',     icon: Mic,         color: 'text-violet-500',  bg: 'bg-violet-500/10' },
  video:    { label: 'Video',     icon: Video,       color: 'text-rose-500',    bg: 'bg-rose-500/10' },
  image:    { label: 'Photos',    icon: ImageIcon,   color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  text:     { label: 'Notes',     icon: AlignLeft,   color: 'text-amber-500',   bg: 'bg-amber-500/10' },
};

export const CATEGORY_ORDER: AssetCategory[] = ['image', 'document', 'audio', 'video', 'text'];

// ─── File preview hook ────────────────────────────────────────────────────────

const API_BASE =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000')
    : '';

/**
 * `authToken`: explicit bearer token override. Defaults to the owner's
 * stored access_token — pass the family session token explicitly when used
 * from a family-facing page, since those never touch the shared access_token
 * key (each session gets its own storage key so they can't collide).
 */
export function useFileBlobUrl(entryId: string | null, authToken?: string | null) {
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

    const token = authToken !== undefined ? authToken : localStorage.getItem('access_token');
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
  }, [entryId, authToken]);

  return { blobUrl, loading, error };
}

// ─── Preview modal ────────────────────────────────────────────────────────────

export function PreviewModal({
  entry,
  onClose,
  authToken,
}: {
  entry: KnowledgeEntry;
  onClose: () => void;
  authToken?: string | null;
}) {
  const cat = classify(entry);
  const hasFile = !!entry.original_content_path;
  const { blobUrl, loading, error } = useFileBlobUrl(hasFile ? entry.id : null, authToken);
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

          {blobUrl && cat === 'image' && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={blobUrl}
              alt={name}
              className="max-h-[70vh] max-w-full rounded-lg object-contain"
            />
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

export function AssetCard({ entry, onOpen }: { entry: KnowledgeEntry; onOpen: () => void }) {
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

export function AssetRow({ entry, onOpen }: { entry: KnowledgeEntry; onOpen: () => void }) {
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

export function CategorySection({
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
