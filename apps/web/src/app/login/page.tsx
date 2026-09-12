'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { KeyRound, Loader2, LogIn } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface LoginResponse {
  verified: boolean;
  message: string;
  owner_id: string | null;
  tokens: { access_token: string; refresh_token: string } | null;
}

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_sign_in_failed: 'Google sign-in failed. Please try again.',
  google_sign_in_expired: 'That Google sign-in link expired. Please try again.',
};

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [mode, setMode] = useState<'password' | 'secret_word' | 'secret_event'>('password');
  const [email, setEmail] = useState('');
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const googleError = searchParams.get('error');
    if (googleError) {
      setError(GOOGLE_ERROR_MESSAGES[googleError] ?? 'Sign-in failed. Please try again.');
    }
  }, [searchParams]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post<LoginResponse>('/api/auth/login', {
        email,
        verification_type: mode,
        value,
      });

      if (res.verified && res.tokens && res.owner_id) {
        api.setTokens(res.tokens.access_token, res.tokens.refresh_token);
        localStorage.setItem('owner_id', res.owner_id);
        router.push('/dashboard');
      } else {
        setError(res.message);
      }
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
            <LogIn className="h-7 w-7 text-primary" />
          </div>
          <CardTitle className="text-2xl">Welcome back</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Sign in to your Replica.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <a href={`${API_BASE}/api/auth/google/start`}>
            <Button type="button" variant="outline" className="w-full gap-2">
              <GoogleIcon className="h-4 w-4" />
              Sign in with Google
            </Button>
          </a>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <div className="h-px flex-1 bg-border" />
            or
            <div className="h-px flex-1 bg-border" />
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="secret">
                  {mode === 'password'
                    ? 'Password'
                    : mode === 'secret_word'
                      ? 'Secret word'
                      : 'Secret event or memory'}
                </Label>
                <button
                  type="button"
                  className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                  onClick={() =>
                    setMode(mode === 'password' ? 'secret_word' : mode === 'secret_word' ? 'secret_event' : 'password')
                  }
                >
                  {mode === 'password' ? 'Use secret word/memory instead' : mode === 'secret_word' ? 'Use secret memory instead' : 'Use password instead'}
                </button>
              </div>
              <Input
                id="secret"
                type="password"
                required
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={mode === 'password' ? 'Enter your password...' : 'Enter your secret...'}
                autoComplete={mode === 'password' ? 'current-password' : 'off'}
              />
            </div>

            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <KeyRound className="mr-2 h-4 w-4" />
              )}
              Sign in
            </Button>
          </form>

          <div className="mt-2 space-y-1 border-t pt-4 text-center text-sm text-muted-foreground">
            <p>
              New here?{' '}
              <Link href="/setup" className="font-medium text-primary underline-offset-4 hover:underline">
                Set up your Replica
              </Link>
            </p>
            <p>
              <Link
                href="/family-access"
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                Family access
              </Link>
              <br />
              <span className="text-xs">
                Access memory of your ancestor or existing family member
              </span>
            </p>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47a5.53 5.53 0 0 1-2.4 3.63v3h3.88c2.27-2.09 3.57-5.17 3.57-8.82Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.95-2.91l-3.88-3c-1.08.72-2.46 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.27v3.11A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.28A7.2 7.2 0 0 1 4.89 12c0-.79.14-1.56.38-2.28V6.61H1.27A12 12 0 0 0 0 12c0 1.94.46 3.77 1.27 5.39l4-3.11Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.69 1.27 6.61l4 3.11C6.22 6.86 8.87 4.75 12 4.75Z"
      />
    </svg>
  );
}
