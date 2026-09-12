'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, MessageCircle, RefreshCw, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import {
  type KnowledgeEntry,
  type AssetCategory,
  classify,
  CATEGORY_ORDER,
  PreviewModal,
  CategorySection,
} from '@/components/assets/shared';

interface FamilyAssetListResponse {
  entries: KnowledgeEntry[];
  total: number;
}

export default function FamilyAssetsPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<KnowledgeEntry | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<FamilyAssetListResponse>('/api/family/assets', {
        authToken: localStorage.getItem('family_token'),
      });
      setEntries(resp.entries ?? []);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : 'Failed to load assets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('family_token');
    if (!token) {
      router.push('/family-access');
      return;
    }
    load();
  }, [router, load]);

  const grouped = useMemo(() => {
    const map = new Map<AssetCategory, KnowledgeEntry[]>(CATEGORY_ORDER.map((c) => [c, []]));
    for (const e of entries) map.get(classify(e))!.push(e);
    return map;
  }, [entries]);

  function handleSignOut() {
    localStorage.removeItem('family_token');
    localStorage.removeItem('family_grantee_name');
    localStorage.removeItem('family_access_level');
    router.push('/family-access');
  }

  return (
    <div className="flex h-full flex-col">
      {preview && (
        <PreviewModal
          entry={preview}
          onClose={() => setPreview(null)}
          authToken={localStorage.getItem('family_token')}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
            <Archive className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">Shared with you</h1>
            <p className="text-xs text-muted-foreground">
              {loading ? 'Loading…' : `${entries.length} ${entries.length === 1 ? 'item' : 'items'}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={load}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => router.push('/family/chat')}
            title="Back to chat"
          >
            <MessageCircle className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handleSignOut}
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
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

        {!loading && !error && entries.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-20 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
              <Archive className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium">Nothing shared yet</p>
            <p className="max-w-xs text-xs text-muted-foreground">
              Photos, recordings, and documents you have access to will show up here.
            </p>
          </div>
        )}

        {!loading && !error && entries.length > 0 && (
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
      </div>
    </div>
  );
}
