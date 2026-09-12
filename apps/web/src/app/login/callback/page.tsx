'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { api } from '@/lib/api';

export default function LoginCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState('');

  useEffect(() => {
    const hash = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash;
    const params = new URLSearchParams(hash);

    const accessToken = params.get('access_token');
    const refreshToken = params.get('refresh_token');
    const ownerId = params.get('owner_id');
    const ownerName = params.get('owner_name');

    if (!accessToken || !refreshToken || !ownerId) {
      setError('Sign-in did not complete. Please try again.');
      return;
    }

    api.setTokens(accessToken, refreshToken);
    localStorage.setItem('owner_id', ownerId);
    if (ownerName) localStorage.setItem('owner_name', ownerName);

    router.replace('/dashboard');
  }, [router]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-4 text-center">
      {error ? (
        <>
          <p className="text-sm text-destructive">{error}</p>
          <a href="/login" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
            Back to sign in
          </a>
        </>
      ) : (
        <>
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Finishing sign-in...</p>
        </>
      )}
    </main>
  );
}
