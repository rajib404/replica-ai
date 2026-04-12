'use client';

import { useEffect, useState, useCallback } from 'react';
import { Database, Trash2, RotateCcw, Server, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { BroadcastForm } from '@/components/admin/broadcast-form';
import { adminApi, ApiError } from '@/lib/admin/api';
import type { MaintenanceJobResponse, BroadcastResponse } from '@/lib/admin/types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const SERVICES = ['api', 'ai', 'postgres', 'redis', 'qdrant', 'ollama'];

function statusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-400';
    case 'failed':
      return 'bg-red-500/20 text-red-700 dark:text-red-400';
    case 'queued':
      return 'bg-amber-500/20 text-amber-700 dark:text-amber-400';
    case 'running':
      return 'bg-blue-500/20 text-blue-700 dark:text-blue-400';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

export function MaintenanceView() {
  const [jobs, setJobs] = useState<MaintenanceJobResponse[]>([]);
  const [broadcasts, setBroadcasts] = useState<BroadcastResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [cachePattern, setCachePattern] = useState('');
  const [restartService, setRestartService] = useState('api');
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsResult, broadcastsResult] = await Promise.all([
        adminApi.get<MaintenanceJobResponse[]>('/maintenance/jobs', { params: { limit: 50 } }),
        adminApi.get<BroadcastResponse[]>('/maintenance/broadcasts', { params: { limit: 20 } }),
      ]);
      setJobs(jobsResult);
      setBroadcasts(broadcastsResult);
    } catch {
      toast.error('Failed to load history');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runAction = async (
    label: string,
    action: () => Promise<MaintenanceJobResponse>,
  ) => {
    setBusy(label);
    try {
      const job = await action();
      toast.success(`${label}: ${job.status}`);
      load();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(`${label} failed: ${err.detail}`);
      } else {
        toast.error(`${label} failed`);
      }
    } finally {
      setBusy(null);
    }
  };

  const triggerBackup = () => {
    if (!confirm('Trigger database backup?')) return;
    runAction('Backup', () => adminApi.post<MaintenanceJobResponse>('/maintenance/backup'));
  };

  const flushCache = () => {
    runAction('Flush Redis', () =>
      adminApi.post<MaintenanceJobResponse>('/maintenance/clear-cache', {
        pattern: cachePattern || null,
      }),
    );
  };

  const restartLoops = () => {
    if (!confirm('Restart background loops?')) return;
    runAction('Restart loops', () =>
      adminApi.post<MaintenanceJobResponse>('/maintenance/restart-loops'),
    );
  };

  const restartSvc = () => {
    if (!confirm(`Restart ${restartService}?`)) return;
    runAction(`Restart ${restartService}`, () =>
      adminApi.post<MaintenanceJobResponse>('/maintenance/restart-service', {
        service: restartService,
      }),
    );
  };

  const runMigrations = () => {
    if (!confirm('Run Prisma migrate deploy?')) return;
    runAction('Migrate', () => adminApi.post<MaintenanceJobResponse>('/maintenance/migrate'));
  };

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-2xl font-bold">Maintenance</h1>
        <p className="text-sm text-muted-foreground">Operational actions and history</p>
      </div>

      <Tabs defaultValue="actions">
        <TabsList>
          <TabsTrigger value="actions">Actions</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="actions" className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Database backup */}
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <Database className="h-5 w-5 text-primary" />
                <h3 className="font-semibold">Database Backup</h3>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">
                Trigger a stub pg_dump job (queued, no real subprocess yet).
              </p>
              <Button onClick={triggerBackup} disabled={busy !== null}>
                Trigger Backup
              </Button>
            </div>

            {/* Cache & loops */}
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <Trash2 className="h-5 w-5 text-primary" />
                <h3 className="font-semibold">Cache & Loops</h3>
              </div>
              <div className="space-y-3">
                <div className="flex gap-2">
                  <Input
                    placeholder="Pattern (empty = all)"
                    value={cachePattern}
                    onChange={(e) => setCachePattern(e.target.value)}
                  />
                  <Button onClick={flushCache} disabled={busy !== null}>
                    Flush Redis
                  </Button>
                </div>
                <Button variant="outline" onClick={restartLoops} disabled={busy !== null}>
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Restart Background Loops
                </Button>
              </div>
            </div>

            {/* Service control */}
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <Server className="h-5 w-5 text-primary" />
                <h3 className="font-semibold">Service Control</h3>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">
                Stub: would run docker compose restart
              </p>
              <div className="flex gap-2">
                <Select value={restartService} onValueChange={setRestartService}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SERVICES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={restartSvc} disabled={busy !== null}>
                  Restart
                </Button>
              </div>
            </div>

            {/* Migrations */}
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <Wrench className="h-5 w-5 text-primary" />
                <h3 className="font-semibold">Migrations</h3>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">
                Stub: would run npx prisma migrate deploy
              </p>
              <Button onClick={runMigrations} disabled={busy !== null}>
                Run Prisma Migrate Deploy
              </Button>
            </div>
          </div>

          <BroadcastForm onSent={load} />
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <div>
            <h3 className="mb-2 text-lg font-semibold">Recent Jobs</h3>
            <div className="rounded-md border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Target</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Started by</TableHead>
                    <TableHead>Started at</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    Array.from({ length: 3 }).map((_, i) => (
                      <TableRow key={i}>
                        {Array.from({ length: 5 }).map((_, j) => (
                          <TableCell key={j}>
                            <Skeleton className="h-4 w-full" />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : jobs.length > 0 ? (
                    jobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="font-mono text-xs">{job.job_type}</TableCell>
                        <TableCell className="font-mono text-xs">{job.target ?? '—'}</TableCell>
                        <TableCell>
                          <Badge className={cn('text-[10px]', statusColor(job.status))}>
                            {job.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">{job.started_by}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(job.started_at).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        No jobs yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-lg font-semibold">Recent Broadcasts</h3>
            <div className="rounded-md border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Push</TableHead>
                    <TableHead>By</TableHead>
                    <TableHead>Sent</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    Array.from({ length: 2 }).map((_, i) => (
                      <TableRow key={i}>
                        {Array.from({ length: 5 }).map((_, j) => (
                          <TableCell key={j}>
                            <Skeleton className="h-4 w-full" />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : broadcasts.length > 0 ? (
                    broadcasts.map((b) => (
                      <TableRow key={b.id}>
                        <TableCell className="font-medium">{b.title}</TableCell>
                        <TableCell>
                          <Badge variant={b.severity === 'critical' ? 'destructive' : 'secondary'}>
                            {b.severity}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">
                          {b.push_sent ? `✓ ${b.push_count}` : '—'}
                        </TableCell>
                        <TableCell className="text-sm">{b.created_by}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(b.created_at).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        No broadcasts yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
