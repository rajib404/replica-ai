'use client';

import { useEffect, useState, useCallback } from 'react';
import { Search, ChevronLeft, ChevronRight, Eye } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { adminApi } from '@/lib/admin/api';
import type { OwnerListResponse, OwnerSummary, OwnerDetailResponse } from '@/lib/admin/types';
import { toast } from 'sonner';

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function OwnersView() {
  const [data, setData] = useState<OwnerListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [selected, setSelected] = useState<OwnerDetailResponse | null>(null);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await adminApi.get<OwnerListResponse>('/owners', {
        params: {
          page,
          page_size: pageSize,
          search: debouncedSearch || undefined,
        },
      });
      setData(result);
    } catch (err) {
      toast.error('Failed to load owners');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, debouncedSearch]);

  useEffect(() => {
    load();
  }, [load]);

  const viewOwner = async (owner: OwnerSummary) => {
    try {
      const detail = await adminApi.get<OwnerDetailResponse>(`/owners/${owner.id}`);
      setSelected(detail);
    } catch {
      toast.error('Failed to load owner detail');
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Owners</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} total` : 'Loading...'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
          <SelectTrigger className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="10">10</SelectItem>
            <SelectItem value="25">25</SelectItem>
            <SelectItem value="50">50</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead className="text-right">Instances</TableHead>
              <TableHead className="text-right">Knowledge</TableHead>
              <TableHead className="text-right">Messages</TableHead>
              <TableHead>Last Active</TableHead>
              <TableHead className="w-10"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : data && data.items.length > 0 ? (
              data.items.map((owner) => (
                <TableRow key={owner.id}>
                  <TableCell className="font-medium">{owner.name ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{owner.email ?? '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">{owner.instance_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{owner.knowledge_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{owner.message_count}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(owner.last_active_at)}
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => viewOwner(owner)}>
                      <Eye className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  No owners found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{selected?.name ?? 'Owner Detail'}</DialogTitle>
            <DialogDescription>{selected?.email}</DialogDescription>
          </DialogHeader>
          {selected && (
            <pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">
              {JSON.stringify(selected, null, 2)}
            </pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
