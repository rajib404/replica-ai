'use client';

import { useState } from 'react';
import { Globe, Loader2, ExternalLink, FileText } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

interface BrowseResultData {
  id: string;
  url: string;
  title: string | null;
  content: string | null;
  summary: string | null;
  status_code: number | null;
  content_length: number;
  fetch_ms: number;
  error: string | null;
}

interface BrowseUrlDialogProps {
  onBrowsed: () => void;
}

export function BrowseUrlDialog({ onBrowsed }: BrowseUrlDialogProps) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BrowseResultData | null>(null);
  const [error, setError] = useState('');

  async function handleBrowse(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setError('');
    setResult(null);
    setLoading(true);

    try {
      const data = await api.post<BrowseResultData>('/api/browse/url', {
        url: url.trim(),
        summarize: true,
      });
      setResult(data);
      onBrowsed();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to fetch page');
      }
    } finally {
      setLoading(false);
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setUrl('');
      setResult(null);
      setError('');
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Globe className="mr-1.5 h-4 w-4" />
          Browse URL
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Browse a URL</DialogTitle>
          <DialogDescription>
            Fetch and summarize any web page.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleBrowse} className="flex gap-2">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com"
            className="flex-1"
          />
          <Button type="submit" disabled={loading || !url.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Go'}
          </Button>
        </form>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-3">
            {result.error ? (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {result.error}
              </div>
            ) : (
              <>
                {/* Title + meta */}
                <div className="space-y-1">
                  {result.title && (
                    <h3 className="font-semibold text-sm">{result.title}</h3>
                  )}
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 hover:underline truncate"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {result.url}
                    </a>
                    {result.status_code && (
                      <Badge variant="outline" className="text-[10px]">
                        {result.status_code}
                      </Badge>
                    )}
                    <span>{result.fetch_ms}ms</span>
                    <span>{(result.content_length / 1024).toFixed(1)}KB</span>
                  </div>
                </div>

                {/* Summary */}
                {result.summary && (
                  <div className="rounded-lg border bg-muted/50 p-3">
                    <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                      <FileText className="h-3 w-3" />
                      Summary
                    </div>
                    <p className="text-sm">{result.summary}</p>
                  </div>
                )}

                {/* Content preview */}
                {result.content && (
                  <ScrollArea className="h-48 rounded border p-3">
                    <p className="whitespace-pre-wrap text-xs text-muted-foreground">
                      {result.content.slice(0, 5000)}
                      {result.content.length > 5000 && '...'}
                    </p>
                  </ScrollArea>
                )}
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
