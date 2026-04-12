'use client';

import { useCallback, useEffect, useState } from 'react';
import { Server, RefreshCw } from 'lucide-react';
import type { ModelInstance } from '@replica-ai/shared';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { InstanceCard } from '@/components/dashboard/instance-card';
import { RegisterInstanceDialog } from '@/components/dashboard/register-instance-dialog';
import { SyncPanel } from '@/components/dashboard/sync-panel';
import { api } from '@/lib/api';

interface InstanceListResponse {
  instances: ModelInstance[];
  total: number;
}

export default function ModelStatusPage() {
  const [instances, setInstances] = useState<ModelInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchInstances = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.get<InstanceListResponse>('/api/instances');
      setInstances(data.instances);
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to load instances');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInstances();
  }, [fetchInstances]);

  async function handlePromote(id: string) {
    try {
      await api.put(`/api/instances/${id}/promote`);
      fetchInstances();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      }
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.delete(`/api/instances/${id}`);
      fetchInstances();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      }
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Server className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Model Instances</h1>
            <p className="text-sm text-muted-foreground">
              Manage your cloud and local model instances.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchInstances} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <RegisterInstanceDialog onRegistered={fetchInstances} />
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && instances.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-muted-foreground">
          Loading instances...
        </div>
      ) : instances.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
          <Server className="h-8 w-8" />
          <p>No instances registered yet.</p>
          <p className="text-xs">Click &quot;Register Instance&quot; to add one.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {instances.map((instance) => (
            <InstanceCard
              key={instance.id}
              instance={instance}
              onPromote={handlePromote}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {instances.length >= 2 && (
        <>
          <Separator />
          <SyncPanel instances={instances} />
        </>
      )}
    </div>
  );
}
