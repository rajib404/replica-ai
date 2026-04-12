'use client';

import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, AlertTriangle, XCircle, ChevronUp } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

type ServiceStatus = 'ok' | 'degraded' | 'unreachable';
type OverallStatus = 'ok' | 'degraded' | 'down';

interface ServiceHealth {
  status: ServiceStatus;
  latency_ms: number | null;
  message: string | null;
  details: Record<string, unknown> | null;
}

interface HealthResponse {
  status: OverallStatus;
  version: string;
  timestamp: string;
  services: Record<string, ServiceHealth>;
}

const POLL_INTERVAL_MS = 30_000;
const SERVICE_LABELS: Record<string, string> = {
  database: 'Database',
  redis: 'Cache',
  ai_service: 'AI Service',
  ollama: 'Local Model',
  qdrant: 'Vector DB',
};

function overallColor(status: OverallStatus | 'loading') {
  switch (status) {
    case 'ok':
      return 'bg-emerald-500';
    case 'degraded':
      return 'bg-amber-500';
    case 'down':
      return 'bg-red-500';
    default:
      return 'bg-muted-foreground';
  }
}

function serviceIcon(status: ServiceStatus) {
  switch (status) {
    case 'ok':
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />;
    case 'degraded':
      return <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />;
    case 'unreachable':
      return <XCircle className="h-3.5 w-3.5 text-red-500" />;
  }
}

export function SystemStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await api.get<HealthResponse>('/api/health');
        if (!cancelled) {
          setHealth(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load status');
          setLoading(false);
        }
      }
    }

    void load();
    const id = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const overall: OverallStatus | 'loading' = loading
    ? 'loading'
    : error
      ? 'down'
      : (health?.status ?? 'down');

  const label =
    overall === 'loading'
      ? 'Checking…'
      : overall === 'ok'
        ? 'All systems operational'
        : overall === 'degraded'
          ? 'Degraded performance'
          : 'Service disruption';

  return (
    <div className="border-t bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex w-full items-center justify-between px-4 py-2 text-xs text-muted-foreground transition hover:bg-accent',
          open && 'bg-accent/50',
        )}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5" />
          <span
            className={cn('h-2 w-2 rounded-full', overallColor(overall))}
            aria-hidden
          />
          <span>{label}</span>
        </div>
        <ChevronUp
          className={cn('h-3.5 w-3.5 transition-transform', !open && 'rotate-180')}
        />
      </button>

      {open && (
        <div className="border-t bg-background px-4 py-3">
          {loading && <p className="text-xs text-muted-foreground">Loading status…</p>}
          {error && (
            <p className="text-xs text-red-500">
              Unable to reach the API. The health endpoint returned: {error}
            </p>
          )}
          {health && (
            <ul className="space-y-1.5">
              {Object.entries(health.services).map(([name, svc]) => (
                <li
                  key={name}
                  className="flex items-center justify-between text-xs"
                >
                  <span className="flex items-center gap-2">
                    {serviceIcon(svc.status)}
                    <span className="text-foreground">
                      {SERVICE_LABELS[name] ?? name}
                    </span>
                  </span>
                  <span className="flex items-center gap-2 text-muted-foreground">
                    {svc.latency_ms !== null && <span>{svc.latency_ms.toFixed(0)} ms</span>}
                    <span
                      className={cn(
                        'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase',
                        svc.status === 'ok' && 'bg-emerald-500/10 text-emerald-600',
                        svc.status === 'degraded' && 'bg-amber-500/10 text-amber-600',
                        svc.status === 'unreachable' && 'bg-red-500/10 text-red-600',
                      )}
                    >
                      {svc.status}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {health && (
            <p className="mt-3 text-[10px] text-muted-foreground">
              v{health.version} · updated {new Date(health.timestamp).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
