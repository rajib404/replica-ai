'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ArrowRightLeft,
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
  Loader2,
} from 'lucide-react';
import type { ModelInstance, SyncLog, SyncConflict } from '@replica-ai/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

interface SyncLogWithConflicts extends SyncLog {
  conflicts: SyncConflict[];
}

interface SyncHistoryResponse {
  syncs: SyncLogWithConflicts[];
  total: number;
}

interface SyncStartedResponse {
  sync_id: string;
  status: string;
  message: string;
}

const STATUS_ICONS: Record<string, typeof CheckCircle2> = {
  completed: CheckCircle2,
  in_progress: Loader2,
  pending: Clock,
  failed: XCircle,
};

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-green-600',
  in_progress: 'text-blue-600',
  pending: 'text-yellow-600',
  failed: 'text-red-600',
};

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function progressPercent(synced: number, total: number): number {
  if (total === 0) return 0;
  return Math.min(100, Math.round((synced / total) * 100));
}

interface SyncPanelProps {
  instances: ModelInstance[];
}

export function SyncPanel({ instances }: SyncPanelProps) {
  const [syncs, setSyncs] = useState<SyncLogWithConflicts[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<SyncHistoryResponse>('/api/sync/history?page_size=10');
      setSyncs(data.syncs);
    } catch {
      // Silently fail — sync panel is secondary UI
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const primary = instances.find((i) => i.isPrimary);
  const targets = instances.filter((i) => !i.isPrimary && i.status !== 'offline');
  const pendingConflicts = syncs.flatMap((s) =>
    s.conflicts.filter((c) => c.resolution === 'pending'),
  );
  const lastSync = syncs.length > 0 ? syncs[0] : null;
  const activeSyncs = syncs.filter((s) => s.status === 'in_progress');

  async function triggerSync(targetId: string) {
    if (!primary) return;
    setSyncing(true);
    setError('');
    try {
      await api.post<SyncStartedResponse>('/api/sync/start', {
        source_instance_id: primary.id,
        target_instance_id: targetId,
        sync_type: 'full',
      });
      await fetchHistory();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Sync failed');
      }
    } finally {
      setSyncing(false);
    }
  }

  async function resolveConflict(conflictId: string, resolution: string) {
    try {
      await api.post(`/api/sync/resolve-conflict/${conflictId}`, { resolution });
      await fetchHistory();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      }
    }
  }

  if (instances.length < 2) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ArrowRightLeft className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Sync</h2>
        </div>
        {primary && targets.length > 0 && (
          <div className="flex gap-2">
            {targets.map((target) => (
              <Button
                key={target.id}
                variant="outline"
                size="sm"
                disabled={syncing}
                onClick={() => triggerSync(target.id)}
              >
                {syncing ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ArrowRightLeft className="mr-1.5 h-3.5 w-3.5" />
                )}
                Sync to {target.hostname}
              </Button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Clock className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Last Sync</p>
              <p className="text-sm font-medium">
                {lastSync ? relativeTime(lastSync.startedAt) : 'Never'}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <ArrowRightLeft className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Active Syncs</p>
              <p className="text-sm font-medium">{activeSyncs.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <AlertTriangle
              className={cn(
                'h-5 w-5',
                pendingConflicts.length > 0 ? 'text-yellow-600' : 'text-muted-foreground',
              )}
            />
            <div>
              <p className="text-xs text-muted-foreground">Conflicts</p>
              <p className="text-sm font-medium">{pendingConflicts.length} pending</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Active sync progress */}
      {activeSyncs.map((sync) => (
        <Card key={sync.id}>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">
                Syncing {sync.syncType === 'model_weights' ? 'model weights' : 'data'}...
              </span>
              <Badge variant="secondary">{sync.syncType}</Badge>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{
                  width: `${progressPercent(sync.entriesSynced, sync.totalEntries)}%`,
                }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {sync.entriesSynced} / {sync.totalEntries} entries
              {sync.bytesTransferred > 0 &&
                ` | ${(sync.bytesTransferred / 1024 / 1024).toFixed(1)} MB transferred`}
            </p>
          </CardContent>
        </Card>
      ))}

      {/* Pending conflicts */}
      {pendingConflicts.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-yellow-600" />
              Conflicts Requiring Resolution
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {pendingConflicts.map((conflict) => (
              <div
                key={conflict.id}
                className="flex items-center justify-between rounded-md border p-3"
              >
                <div>
                  <p className="text-sm font-medium">
                    {conflict.entryType.replace('_', ' ')}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Entry: {conflict.entryId.slice(0, 12)}...
                  </p>
                </div>
                <div className="flex gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resolveConflict(conflict.id, 'keep_source')}
                  >
                    Keep Source
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resolveConflict(conflict.id, 'keep_target')}
                  >
                    Keep Target
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => resolveConflict(conflict.id, 'keep_both')}
                  >
                    Keep Both
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Recent sync history */}
      {!loading && syncs.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Recent Syncs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {syncs.slice(0, 5).map((sync) => {
                const Icon = STATUS_ICONS[sync.status] ?? Clock;
                return (
                  <div
                    key={sync.id}
                    className="flex items-center justify-between text-sm"
                  >
                    <div className="flex items-center gap-2">
                      <Icon
                        className={cn(
                          'h-4 w-4',
                          STATUS_COLORS[sync.status],
                          sync.status === 'in_progress' && 'animate-spin',
                        )}
                      />
                      <span className="capitalize">{sync.syncType.replace('_', ' ')}</span>
                      <span className="text-muted-foreground">
                        {sync.entriesSynced} entries
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {sync.conflicts.length > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {sync.conflicts.filter((c) => c.resolution === 'pending').length}{' '}
                          conflicts
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {relativeTime(sync.startedAt)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
