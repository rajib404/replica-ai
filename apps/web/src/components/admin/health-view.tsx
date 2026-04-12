'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { RefreshCw, CheckCircle2, AlertTriangle, XCircle, HelpCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { adminApi } from '@/lib/admin/api';
import type { ServiceHealthEntry, ServiceHealthStatus } from '@/lib/admin/types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const POLL_INTERVAL_MS = 10_000;

function statusIcon(status: ServiceHealthStatus) {
  switch (status) {
    case 'healthy':
      return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
    case 'degraded':
      return <AlertTriangle className="h-5 w-5 text-amber-500" />;
    case 'down':
      return <XCircle className="h-5 w-5 text-red-500" />;
    default:
      return <HelpCircle className="h-5 w-5 text-muted-foreground" />;
  }
}

function statusColor(status: ServiceHealthStatus): string {
  switch (status) {
    case 'healthy':
      return 'bg-emerald-500';
    case 'degraded':
      return 'bg-amber-500';
    case 'down':
      return 'bg-red-500';
    default:
      return 'bg-muted-foreground';
  }
}

export function HealthView() {
  const [services, setServices] = useState<ServiceHealthEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [history, setHistory] = useState<Record<string, number[]>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await adminApi.get<ServiceHealthEntry[]>('/health/services');
      setServices(result);
      setHistory((prev) => {
        const next = { ...prev };
        for (const svc of result) {
          const arr = next[svc.name] ? [...next[svc.name]] : [];
          arr.push(svc.response_time_ms ?? 0);
          if (arr.length > 30) arr.shift();
          next[svc.name] = arr;
        }
        return next;
      });
    } catch (err) {
      toast.error('Failed to load health');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (autoRefresh) {
      intervalRef.current = setInterval(load, POLL_INTERVAL_MS);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, load]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">System Health</h1>
          <p className="text-sm text-muted-foreground">
            {autoRefresh ? `Auto-refreshing every ${POLL_INTERVAL_MS / 1000}s` : 'Auto-refresh paused'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh((v) => !v)}
          >
            {autoRefresh ? 'Pause' : 'Resume'}
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh now
          </Button>
        </div>
      </div>

      {loading && !services ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : services ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((svc) => {
            const sparkline = history[svc.name] ?? [];
            const max = Math.max(...sparkline, 1);
            return (
              <div key={svc.name} className="rounded-lg border bg-card p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {statusIcon(svc.status)}
                    <span className="font-semibold capitalize">{svc.name}</span>
                  </div>
                  <div className={cn('h-2 w-2 rounded-full', statusColor(svc.status))} />
                </div>
                <div className="mt-3 text-2xl font-bold tabular-nums">
                  {svc.response_time_ms != null ? `${svc.response_time_ms.toFixed(0)} ms` : '—'}
                </div>
                {svc.last_error && (
                  <p className="mt-2 line-clamp-2 text-xs text-red-500" title={svc.last_error}>
                    {svc.last_error}
                  </p>
                )}
                {sparkline.length > 1 && (
                  <div className="mt-3 flex h-8 items-end gap-0.5">
                    {sparkline.map((v, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-sm bg-primary/40"
                        style={{ height: `${(v / max) * 100}%` }}
                      />
                    ))}
                  </div>
                )}
                <div className="mt-2 text-xs text-muted-foreground">
                  {new Date(svc.checked_at).toLocaleTimeString()}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
