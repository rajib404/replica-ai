'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Users,
  BookOpen,
  Server,
  MessageSquare,
  Cpu,
  HardDrive,
  Activity,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { StatCard } from '@/components/admin/stat-card';
import { adminApi } from '@/lib/admin/api';
import type { SystemOverviewResponse } from '@/lib/admin/types';
import { toast } from 'sonner';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function OverviewView() {
  const [data, setData] = useState<SystemOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await adminApi.get<SystemOverviewResponse>('/overview');
      setData(result);
    } catch (err) {
      toast.error('Failed to load overview');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">System Overview</h1>
          <p className="text-sm text-muted-foreground">Snapshot of system health and usage</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total Owners" value={data.total_owners} icon={Users} />
            <StatCard
              label="Active Instances"
              value={data.active_instances}
              icon={Server}
            />
            <StatCard
              label="Knowledge Entries"
              value={data.total_knowledge_entries.toLocaleString()}
              icon={BookOpen}
            />
            <StatCard
              label="Total Messages"
              value={data.total_messages.toLocaleString()}
              icon={MessageSquare}
              subtext={`${data.total_conversations.toLocaleString()} conversations`}
            />
          </div>

          <div>
            <h2 className="mb-3 text-lg font-semibold">Resources</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="CPU"
                value={data.resources.cpu_percent != null ? `${data.resources.cpu_percent.toFixed(1)}%` : '—'}
                icon={Cpu}
              />
              <StatCard
                label="Memory"
                value={
                  data.resources.memory_percent != null
                    ? `${data.resources.memory_percent.toFixed(1)}%`
                    : '—'
                }
                icon={Activity}
                subtext={
                  data.resources.memory_used_mb != null && data.resources.memory_total_mb != null
                    ? `${data.resources.memory_used_mb.toFixed(0)} / ${data.resources.memory_total_mb.toFixed(0)} MB`
                    : undefined
                }
              />
              <StatCard
                label="Disk"
                value={
                  data.resources.disk_percent != null
                    ? `${data.resources.disk_percent.toFixed(1)}%`
                    : '—'
                }
                icon={HardDrive}
                subtext={
                  data.resources.disk_used_gb != null && data.resources.disk_total_gb != null
                    ? `${data.resources.disk_used_gb.toFixed(1)} / ${data.resources.disk_total_gb.toFixed(1)} GB`
                    : undefined
                }
              />
              <StatCard
                label="Uptime"
                value={formatUptime(data.resources.uptime_seconds)}
                icon={Clock}
                subtext={`Storage: ${formatBytes(data.approximate_storage_bytes)}`}
              />
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-md border bg-card p-8 text-center text-muted-foreground">
          No data available
        </div>
      )}
    </div>
  );
}
