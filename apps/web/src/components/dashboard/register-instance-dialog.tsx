'use client';

import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

const CAPABILITY_OPTIONS = ['generate', 'embed', 'ingest'] as const;

interface RegisteredResult {
  instance: { id: string; hostname: string };
  auth_token: string;
}

interface RegisterInstanceDialogProps {
  onRegistered: () => void;
}

export function RegisterInstanceDialog({ onRegistered }: RegisterInstanceDialogProps) {
  const [open, setOpen] = useState(false);
  const [hostname, setHostname] = useState('');
  const [instanceType, setInstanceType] = useState<'cloud' | 'local'>('local');
  const [apiUrl, setApiUrl] = useState('');
  const [capabilities, setCapabilities] = useState<string[]>([...CAPABILITY_OPTIONS]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RegisteredResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  function toggleCapability(cap: string) {
    setCapabilities((prev) =>
      prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data = await api.post<RegisteredResult>('/api/instances/register', {
        hostname,
        instance_type: instanceType,
        api_url: apiUrl || null,
        capabilities,
      });
      setResult(data);
      onRegistered();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to register instance');
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function copyToken() {
    if (!result) return;
    await navigator.clipboard.writeText(result.auth_token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setHostname('');
      setInstanceType('local');
      setApiUrl('');
      setCapabilities([...CAPABILITY_OPTIONS]);
      setResult(null);
      setError('');
      setCopied(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>Register Instance</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        {result ? (
          <>
            <DialogHeader>
              <DialogTitle>Instance Registered</DialogTitle>
              <DialogDescription>
                Save this auth token now — it will not be shown again.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <Label className="text-xs text-muted-foreground">Instance ID</Label>
                <p className="text-sm font-mono">{result.instance.id}</p>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Auth Token</Label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded bg-muted p-2 text-xs">
                    {result.auth_token}
                  </code>
                  <Button variant="outline" size="icon" onClick={copyToken}>
                    {copied ? (
                      <Check className="h-4 w-4 text-green-600" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <DialogHeader>
              <DialogTitle>Register Instance</DialogTitle>
              <DialogDescription>
                Add a new cloud or local model instance.
              </DialogDescription>
            </DialogHeader>
            <div className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="hostname">Hostname</Label>
                <Input
                  id="hostname"
                  value={hostname}
                  onChange={(e) => setHostname(e.target.value)}
                  placeholder="my-desktop"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="instance-type">Type</Label>
                <div className="flex gap-3">
                  {(['local', 'cloud'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setInstanceType(t)}
                      className={`rounded-md border px-4 py-2 text-sm font-medium transition-colors ${
                        instanceType === t
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input bg-background hover:bg-accent'
                      }`}
                    >
                      {t === 'local' ? 'Local' : 'Cloud'}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="api-url">API URL (optional)</Label>
                <Input
                  id="api-url"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="http://192.168.1.50:8100"
                />
              </div>

              <div className="space-y-2">
                <Label>Capabilities</Label>
                <div className="flex gap-3">
                  {CAPABILITY_OPTIONS.map((cap) => (
                    <label
                      key={cap}
                      className="flex cursor-pointer items-center gap-1.5 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={capabilities.includes(cap)}
                        onChange={() => toggleCapability(cap)}
                        className="h-4 w-4 rounded border-input"
                      />
                      {cap}
                    </label>
                  ))}
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
            <DialogFooter className="mt-6">
              <Button type="submit" disabled={submitting || !hostname}>
                {submitting ? 'Registering...' : 'Register'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
