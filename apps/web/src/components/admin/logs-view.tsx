'use client';

import { useEffect, useState, useCallback, useRef, Fragment } from 'react';
import { RefreshCw, ChevronRight, ChevronDown } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
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
import { adminApi } from '@/lib/admin/api';
import type { LogsResponse, LogLevel, LogEntry } from '@/lib/admin/types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const POLL_INTERVAL_MS = 5_000;
const LEVELS: ('ALL' | LogLevel)[] = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

function levelClass(level: LogLevel): string {
  switch (level) {
    case 'CRITICAL':
      return 'bg-red-600 text-white';
    case 'ERROR':
      return 'bg-red-500/20 text-red-700 dark:text-red-400';
    case 'WARNING':
      return 'bg-amber-500/20 text-amber-700 dark:text-amber-400';
    case 'INFO':
      return 'bg-blue-500/20 text-blue-700 dark:text-blue-400';
    case 'DEBUG':
      return 'bg-muted text-muted-foreground';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

export function LogsView() {
  const [data, setData] = useState<LogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [level, setLevel] = useState<'ALL' | LogLevel>('ALL');
  const [logger, setLogger] = useState('');
  const [search, setSearch] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await adminApi.get<LogsResponse>('/logs', {
        params: {
          level: level === 'ALL' ? undefined : level,
          logger: logger || undefined,
          search: search || undefined,
          limit: 500,
        },
      });
      setData(result);
    } catch {
      toast.error('Failed to load logs');
    } finally {
      setLoading(false);
    }
  }, [level, logger, search]);

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

  const toggleExpand = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Logs</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `Showing ${data.items.length} of ${data.total}` : 'Loading...'}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={level} onValueChange={(v) => setLevel(v as 'ALL' | LogLevel)}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEVELS.map((lvl) => (
              <SelectItem key={lvl} value={lvl}>
                {lvl}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          placeholder="Logger substring..."
          value={logger}
          onChange={(e) => setLogger(e.target.value)}
          className="max-w-xs"
        />

        <Input
          placeholder="Search messages..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />

        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>

        <div className="flex items-center gap-2">
          <Switch checked={autoRefresh} onCheckedChange={setAutoRefresh} id="auto-refresh" />
          <label htmlFor="auto-refresh" className="text-sm">
            Auto-refresh 5s
          </label>
        </div>
      </div>

      <div className="rounded-md border bg-card">
        <div className="max-h-[calc(100vh-280px)] overflow-y-auto">
          <Table>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead className="w-44">Timestamp</TableHead>
                <TableHead className="w-24">Level</TableHead>
                <TableHead className="w-48">Logger</TableHead>
                <TableHead>Message</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && !data ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 5 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : data && data.items.length > 0 ? (
                data.items.map((entry: LogEntry, idx) => {
                  const isExpanded = expanded.has(idx);
                  const hasExc = !!entry.exc_info;
                  return (
                    <Fragment key={`${entry.timestamp}-${idx}`}>
                      <TableRow
                        className={cn(hasExc && 'cursor-pointer')}
                        onClick={hasExc ? () => toggleExpand(idx) : undefined}
                      >
                        <TableCell>
                          {hasExc && (isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          ))}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {new Date(entry.timestamp).toLocaleString()}
                        </TableCell>
                        <TableCell>
                          <Badge className={cn('font-mono text-[10px]', levelClass(entry.level))}>
                            {entry.level}
                          </Badge>
                        </TableCell>
                        <TableCell className="truncate font-mono text-xs">
                          {entry.logger_name}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{entry.message}</TableCell>
                      </TableRow>
                      {isExpanded && hasExc && (
                        <TableRow>
                          <TableCell colSpan={5} className="bg-muted/50">
                            <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-red-500">
                              {entry.exc_info}
                            </pre>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No log entries
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
