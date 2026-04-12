'use client';

import { Cloud, Monitor, Star, Trash2, ArrowUpCircle } from 'lucide-react';
import type { ModelInstance } from '@replica-ai/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-500/15 text-green-700 border-green-500/25',
  dormant: 'bg-yellow-500/15 text-yellow-700 border-yellow-500/25',
  offline: 'bg-red-500/15 text-red-700 border-red-500/25',
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

interface InstanceCardProps {
  instance: ModelInstance;
  onPromote: (id: string) => void;
  onDelete: (id: string) => void;
}

export function InstanceCard({ instance, onPromote, onDelete }: InstanceCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          {instance.instanceType === 'cloud' ? (
            <Cloud className="h-5 w-5 text-muted-foreground" />
          ) : (
            <Monitor className="h-5 w-5 text-muted-foreground" />
          )}
          <CardTitle className="text-base">{instance.hostname}</CardTitle>
          {instance.isPrimary && <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />}
        </div>
        <Badge className={cn('capitalize', STATUS_COLORS[instance.status] ?? '')}>
          {instance.status}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className="text-xs capitalize">
            {instance.instanceType}
          </Badge>
          {instance.capabilities?.map((cap) => (
            <Badge key={cap} variant="secondary" className="text-xs">
              {cap}
            </Badge>
          ))}
        </div>

        {instance.apiUrl && (
          <p className="truncate text-xs text-muted-foreground">{instance.apiUrl}</p>
        )}

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Last heartbeat: {relativeTime(instance.lastHeartbeatAt)}</span>
          <span>v{instance.version}</span>
        </div>

        <div className="flex gap-2 pt-1">
          {!instance.isPrimary && (
            <Button variant="outline" size="sm" onClick={() => onPromote(instance.id)}>
              <ArrowUpCircle className="mr-1.5 h-3.5 w-3.5" />
              Promote
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => onDelete(instance.id)}>
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Remove
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
