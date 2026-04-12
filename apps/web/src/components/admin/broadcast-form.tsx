'use client';

import { useState, type FormEvent } from 'react';
import { Megaphone } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { adminApi, ApiError } from '@/lib/admin/api';
import type { BroadcastRequest, BroadcastResponse, BroadcastSeverity } from '@/lib/admin/types';
import { toast } from 'sonner';

interface BroadcastFormProps {
  onSent: () => void;
}

export function BroadcastForm({ onSent }: BroadcastFormProps) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [severity, setSeverity] = useState<BroadcastSeverity>('info');
  const [sendPush, setSendPush] = useState(true);
  const [expiresAt, setExpiresAt] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitting(true);
    const payload: BroadcastRequest = {
      title,
      body,
      severity,
      send_push: sendPush,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    };
    try {
      const result = await adminApi.post<BroadcastResponse>('/maintenance/broadcast', payload);
      toast.success(
        `Broadcast sent${result.push_sent ? ` to ${result.push_count} subscribers` : ''}`,
      );
      setTitle('');
      setBody('');
      setExpiresAt('');
      onSent();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error('Failed to send broadcast');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Megaphone className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">Broadcast Notification</h3>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">Title</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Severity</label>
            <Select value={severity} onValueChange={(v) => setSeverity(v as BroadcastSeverity)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="info">Info</SelectItem>
                <SelectItem value="warning">Warning</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Body</label>
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} required />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">Expires at (optional)</label>
            <Input
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <div className="flex w-full items-center justify-between rounded-md border p-3">
              <span className="text-sm font-medium">Send push notification</span>
              <Switch checked={sendPush} onCheckedChange={setSendPush} />
            </div>
          </div>
        </div>

        <Button type="submit" disabled={submitting}>
          {submitting ? 'Sending...' : 'Send Broadcast'}
        </Button>
      </form>
    </div>
  );
}
