'use client';

import {
  Eye,
  Pause,
  Play,
  Trash2,
  AlertTriangle,
  Clock,
  Hash,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-500/15 text-green-700 border-green-500/25',
  paused: 'bg-gray-500/15 text-gray-700 border-gray-500/25',
  triggered: 'bg-orange-500/15 text-orange-700 border-orange-500/25',
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

interface Monitor {
  id: string;
  url: string;
  keywords: string[];
  interval_hours: number;
  status: string;
  last_checked_at: string | null;
  last_triggered_at: string | null;
  trigger_reason: string | null;
  check_count: number;
  created_at: string;
}

interface MonitorCardProps {
  monitor: Monitor;
  onToggle: (id: string, status: string) => void;
  onDelete: (id: string) => void;
}

export function MonitorCard({ monitor, onToggle, onDelete }: MonitorCardProps) {
  const isActive = monitor.status === 'active';
  const isTriggered = monitor.status === 'triggered';

  return (
    <Card className={cn(isTriggered && 'ring-2 ring-orange-500')}>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Eye className="h-4 w-4 text-muted-foreground shrink-0" />
          <CardTitle className="text-sm truncate">{monitor.url}</CardTitle>
        </div>
        <Badge className={cn('text-xs shrink-0 ml-2', STATUS_COLORS[monitor.status] ?? '')}>
          {monitor.status}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Keywords */}
        {monitor.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {monitor.keywords.map((kw) => (
              <Badge key={kw} variant="secondary" className="text-xs">
                <Hash className="mr-0.5 h-2.5 w-2.5" />
                {kw}
              </Badge>
            ))}
          </div>
        )}

        {/* Trigger alert */}
        {isTriggered && monitor.trigger_reason && (
          <div className="flex items-start gap-2 rounded-md border border-orange-500/50 bg-orange-500/10 p-2 text-xs text-orange-700">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>{monitor.trigger_reason}</span>
          </div>
        )}

        {/* Stats */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Every {monitor.interval_hours}h
          </span>
          <span>{monitor.check_count} checks</span>
          <span>Last: {relativeTime(monitor.last_checked_at)}</span>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              onToggle(monitor.id, isActive || isTriggered ? 'paused' : 'active')
            }
          >
            {isActive || isTriggered ? (
              <>
                <Pause className="mr-1.5 h-3.5 w-3.5" />
                Pause
              </>
            ) : (
              <>
                <Play className="mr-1.5 h-3.5 w-3.5" />
                Resume
              </>
            )}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onDelete(monitor.id)}>
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
