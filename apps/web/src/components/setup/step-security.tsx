'use client';

import { useState } from 'react';
import { Eye, EyeOff, KeyRound, BookOpen, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';
import type { SetupData, SetupResult } from '@/components/setup/setup-wizard';

interface StepSecurityProps {
  data: SetupData;
  onChange: (partial: Partial<SetupData>) => void;
  onBack: () => void;
  onNext: (result: SetupResult) => void;
}

export function StepSecurity({ data, onChange, onBack, onNext }: StepSecurityProps) {
  const [showSecret, setShowSecret] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isValid = data.password.trim().length >= 8 && data.secretValue.trim().length >= 3;

  async function handleSubmit() {
    setLoading(true);
    setError('');

    try {
      const body: Record<string, string> = {
        name: data.name,
        preferred_language: data.preferredLanguage,
        password: data.password,
      };
      if (data.email) body.email = data.email;
      else body.email = `${data.name.toLowerCase().replace(/[^a-z0-9]/g, '.')}@replica-ai.dev`;

      if (data.verificationMethod === 'secret_word') {
        body.secret_word = data.secretValue;
      } else {
        body.secret_event = data.secretValue;
      }

      const res = await api.post<{
        owner_id: string;
        tokens: { access_token: string; refresh_token: string };
        connect_url: string;
        qr_code_base64: string;
      }>('/api/auth/setup', body);

      api.setTokens(res.tokens.access_token, res.tokens.refresh_token);
      localStorage.setItem('owner_id', res.owner_id);
      localStorage.setItem('owner_name', data.name);

      onNext({
        ownerId: res.owner_id,
        accessToken: res.tokens.access_token,
        refreshToken: res.tokens.refresh_token,
        connectUrl: res.connect_url,
        qrCodeBase64: res.qr_code_base64,
      });
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to create account. Is the API server running?');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-xl font-bold">Security Setup</h2>
        <p className="text-sm text-muted-foreground">
          Set your sign-in password, then choose how family members can recover access if they
          ever need to.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="At least 8 characters"
              value={data.password}
              onChange={(e) => onChange({ password: e.target.value })}
              className="pr-10"
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            This is what you&apos;ll use to sign in. Minimum 8 characters.
          </p>
        </div>

        <div className="space-y-3 border-t pt-4">
          <div>
            <Label>Family Recovery Method</Label>
            <p className="text-xs text-muted-foreground">
              A separate secret &mdash; not your password &mdash; that you can share with family so
              they can recover access to your Replica if you&apos;re ever unable to sign in
              yourself.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => onChange({ verificationMethod: 'secret_word', secretValue: '' })}
              className={`flex flex-col items-center gap-2 rounded-lg border p-4 text-sm transition-colors ${
                data.verificationMethod === 'secret_word'
                  ? 'border-primary bg-primary/5'
                  : 'hover:bg-accent'
              }`}
            >
              <KeyRound className="h-5 w-5" />
              <span className="font-medium">Secret Word</span>
              <span className="text-xs text-muted-foreground">A password or passphrase</span>
            </button>

            <button
              type="button"
              onClick={() => onChange({ verificationMethod: 'secret_event', secretValue: '' })}
              className={`flex flex-col items-center gap-2 rounded-lg border p-4 text-sm transition-colors ${
                data.verificationMethod === 'secret_event'
                  ? 'border-primary bg-primary/5'
                  : 'hover:bg-accent'
              }`}
            >
              <BookOpen className="h-5 w-5" />
              <span className="font-medium">Secret Event</span>
              <span className="text-xs text-muted-foreground">A shared memory only family knows</span>
            </button>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="secret">
            {data.verificationMethod === 'secret_word'
              ? 'Enter your secret word or phrase'
              : 'Describe the shared event or memory'}
          </Label>
          <div className="relative">
            <Input
              id="secret"
              type={showSecret ? 'text' : 'password'}
              placeholder={
                data.verificationMethod === 'secret_word'
                  ? 'e.g., butterfly garden 2019'
                  : 'e.g., the restaurant where we celebrated mom\'s 60th birthday'
              }
              value={data.secretValue}
              onChange={(e) => onChange({ secretValue: e.target.value })}
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowSecret(!showSecret)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">Minimum 3 characters</p>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack} disabled={loading} className="flex-1">
          Back
        </Button>
        <Button onClick={handleSubmit} disabled={!isValid || loading} className="flex-1">
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Create My Replica
        </Button>
      </div>
    </div>
  );
}
