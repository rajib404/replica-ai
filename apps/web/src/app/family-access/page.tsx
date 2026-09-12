'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Heart, KeyRound, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

interface FamilyLoginResponse {
  verified: boolean;
  message: string;
  session_token: string | null;
  access_level: string | null;
  grantee_name: string | null;
  topic_restrictions: { allowed: string[]; blocked: string[] } | null;
  time_restrictions: Record<string, unknown> | null;
}

export default function FamilyAccessPage() {
  const router = useRouter();

  const [familyCode, setFamilyCode] = useState('');
  const [name, setName] = useState('');
  const [secret, setSecret] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post<FamilyLoginResponse>('/api/access/family-login', {
        family_code: familyCode.trim(),
        grantee_name: name.trim(),
        verification_value: secret,
      });

      if (res.verified && res.session_token) {
        localStorage.setItem('family_token', res.session_token);
        localStorage.setItem('family_grantee_name', res.grantee_name ?? '');
        localStorage.setItem('family_access_level', res.access_level ?? '');
        router.push('/family/chat');
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
            <Heart className="h-7 w-7 text-primary" />
          </div>
          <CardTitle className="text-2xl">Family Access</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Access memory of your ancestor or existing family member
          </p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="family-code">Family code</Label>
              <Input
                id="family-code"
                required
                value={familyCode}
                onChange={(e) => setFamilyCode(e.target.value)}
                placeholder="e.g. V6Q6-PMD6"
                autoComplete="off"
                className="uppercase"
              />
              <p className="text-xs text-muted-foreground">
                The code your family member shared with you.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="grantee-name">Your name</Label>
              <Input
                id="grantee-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="The name they know you by"
                autoComplete="name"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="secret">Secret word</Label>
              <Input
                id="secret"
                type="password"
                required
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Enter the secret word..."
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
              Connect
            </Button>
          </form>

          <div className="mt-6 border-t pt-4 text-center text-sm text-muted-foreground">
            <p>
              Are you the owner?{' '}
              <Link href="/login" className="font-medium text-primary underline-offset-4 hover:underline">
                Sign in
              </Link>
            </p>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
