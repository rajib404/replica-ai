'use client';

import { useEffect, useState } from 'react';
import { Check, Copy, KeyRound, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';

interface FamilyCodeResponse {
  family_code: string;
}

export function FamilyCodeCard() {
  const [code, setCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<FamilyCodeResponse>('/api/access/family-code');
        setCode(res.family_code);
      } catch {
        setError('Failed to load your family code.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleRegenerate() {
    if (
      !window.confirm(
        'Generate a new family code? Anyone still using the old code will no longer be able to connect.',
      )
    ) {
      return;
    }
    setRegenerating(true);
    setError('');
    try {
      const res = await api.post<FamilyCodeResponse>('/api/access/family-code/regenerate');
      setCode(res.family_code);
    } catch {
      setError('Failed to regenerate your family code.');
    } finally {
      setRegenerating(false);
    }
  }

  async function copyCode() {
    if (!code) return;
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4" /> Family Access Code
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Share this code with family members, alongside the name and secret word you set on
          each access rule below. It never expires, so it works even years from now &mdash; no
          invite link needed.
        </p>
      </CardHeader>
      <CardContent className="flex items-center gap-2">
        {loading ? (
          <span className="text-sm text-muted-foreground">Loading...</span>
        ) : code ? (
          <>
            <code className="rounded-md border bg-muted px-3 py-1.5 text-lg font-semibold tracking-wide">
              {code}
            </code>
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={copyCode}>
              {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRegenerate}
              disabled={regenerating}
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${regenerating ? 'animate-spin' : ''}`} />
              Regenerate
            </Button>
          </>
        ) : (
          <span className="text-sm text-destructive">{error}</span>
        )}
      </CardContent>
    </Card>
  );
}
