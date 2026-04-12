'use client';

import { useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Heart, Shield, Lock, ArrowRight, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

interface VerifyResponse {
  verified: boolean;
  message: string;
  session_token: string | null;
  access_level: string | null;
  grantee_name: string | null;
  topic_restrictions: { allowed: string[]; blocked: string[] } | null;
  time_restrictions: { days: string[]; start_hour: number; end_hour: number; timezone: string } | null;
}

export default function FamilyJoinPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const inviteToken = searchParams.get('token') ?? '';

  const [step, setStep] = useState<'welcome' | 'verify' | 'success' | 'error'>('welcome');
  const [verificationValue, setVerificationValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [verifyMessage, setVerifyMessage] = useState('');
  const [sessionInfo, setSessionInfo] = useState<{
    grantee_name: string;
    access_level: string;
  } | null>(null);

  async function handleVerify(withValue?: string) {
    setLoading(true);
    setError('');
    try {
      const resp = await api.post<VerifyResponse>('/api/access/verify', {
        invite_token: inviteToken,
        verification_value: (withValue ?? verificationValue) || null,
      });

      if (resp.verified && resp.session_token) {
        // Store the family session token
        localStorage.setItem('family_token', resp.session_token);
        localStorage.setItem('family_grantee_name', resp.grantee_name ?? '');
        localStorage.setItem('family_access_level', resp.access_level ?? '');

        // Also set as the regular access_token so the api client picks it up
        localStorage.setItem('access_token', resp.session_token);

        setSessionInfo({
          grantee_name: resp.grantee_name ?? 'Friend',
          access_level: resp.access_level ?? 'limited',
        });
        setStep('success');

        // Redirect to chat after a short delay
        setTimeout(() => {
          router.push('/family/chat');
        }, 2000);
      } else {
        // Verification required or failed
        if (resp.message.includes('Verification required')) {
          setVerifyMessage(resp.message);
          setStep('verify');
        } else {
          setError(resp.message);
          setStep('error');
        }
      }
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Something went wrong. Please try again.');
      }
      setStep('error');
    } finally {
      setLoading(false);
    }
  }

  if (!inviteToken) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
        <Lock className="h-12 w-12 text-muted-foreground" />
        <h1 className="text-2xl font-bold">Invalid Link</h1>
        <p className="text-muted-foreground">
          This invite link is missing or invalid. Please ask for a new one.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center bg-gradient-to-b from-background to-muted/30 p-4">
      <Card className="w-full max-w-md">
        {step === 'welcome' && (
          <>
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                <Heart className="h-8 w-8 text-primary" />
              </div>
              <CardTitle className="text-2xl">Welcome</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">
                You&apos;ve been invited to talk with a loved one&apos;s AI Replica.
                This AI has been trained on their memories, stories, and personality.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border bg-muted/50 p-4 text-center text-sm text-muted-foreground">
                <p>Your conversations are private and respectful.</p>
                <p className="mt-1">The AI will share what it knows while protecting private information.</p>
              </div>
              <Button className="w-full" onClick={() => handleVerify()} disabled={loading}>
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ArrowRight className="mr-2 h-4 w-4" />
                )}
                Continue
              </Button>
            </CardContent>
          </>
        )}

        {step === 'verify' && (
          <>
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-orange-500/10">
                <Shield className="h-8 w-8 text-orange-500" />
              </div>
              <CardTitle className="text-xl">Verification Required</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">{verifyMessage}</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="verification">Your Answer</Label>
                <Input
                  id="verification"
                  type="password"
                  value={verificationValue}
                  onChange={(e) => setVerificationValue(e.target.value)}
                  placeholder="Enter the secret word or event..."
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleVerify();
                  }}
                />
              </div>
              <Button
                className="w-full"
                onClick={() => handleVerify()}
                disabled={loading || !verificationValue}
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Shield className="mr-2 h-4 w-4" />
                )}
                Verify
              </Button>
            </CardContent>
          </>
        )}

        {step === 'success' && sessionInfo && (
          <>
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
                <Heart className="h-8 w-8 text-green-500" />
              </div>
              <CardTitle className="text-xl">Welcome, {sessionInfo.grantee_name}!</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">
                You&apos;re now connected. Redirecting you to the chat...
              </p>
            </CardHeader>
            <CardContent>
              <div className="flex justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              </div>
            </CardContent>
          </>
        )}

        {step === 'error' && (
          <>
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
                <Lock className="h-8 w-8 text-destructive" />
              </div>
              <CardTitle className="text-xl">Access Denied</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">{error}</p>
            </CardHeader>
            <CardContent>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  setError('');
                  setStep('welcome');
                }}
              >
                Try Again
              </Button>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
