'use client';

import { useState, useEffect, useRef } from 'react';
import { Shield, ShieldAlert, Lock, Clock, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ChallengeData, ChallengeResultData } from '@/lib/use-chat-socket';

interface ChallengeModalProps {
  challenge: ChallengeData;
  onRespond: (challengeId: string, answer?: string, method?: string, value?: string) => void;
  result: ChallengeResultData | null;
  onDismiss: () => void;
}

export function ChallengeModal({ challenge, onRespond, result, onDismiss }: ChallengeModalProps) {
  const [answer, setAnswer] = useState('');
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null);
  const [secretValue, setSecretValue] = useState('');
  const [timeLeft, setTimeLeft] = useState(challenge.timeout_seconds);
  const inputRef = useRef<HTMLInputElement>(null);

  // Countdown timer
  useEffect(() => {
    if (result) return;
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [result]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, [selectedMethod]);

  function handleSubmit() {
    if (challenge.challenge_type === 'soft') {
      onRespond(challenge.challenge_id, answer);
    } else if (selectedMethod === 'secret_word') {
      onRespond(challenge.challenge_id, undefined, 'secret_word', secretValue);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  }

  const isExpired = timeLeft <= 0 && !result;
  const isSoft = challenge.challenge_type === 'soft';
  const IconComponent = isSoft ? Shield : ShieldAlert;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <Card className="mx-4 w-full max-w-md shadow-2xl">
        <CardHeader className="space-y-2 pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IconComponent className={`h-5 w-5 ${isSoft ? 'text-yellow-500' : 'text-red-500'}`} />
              <CardTitle className="text-lg">
                {isSoft ? 'Quick Identity Check' : 'Identity Verification Required'}
              </CardTitle>
            </div>
            {!result && (
              <div className={`flex items-center gap-1 text-xs ${timeLeft < 15 ? 'text-red-500' : 'text-muted-foreground'}`}>
                <Clock className="h-3 w-3" />
                {Math.floor(timeLeft / 60)}:{(timeLeft % 60).toString().padStart(2, '0')}
              </div>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Result feedback */}
          {result && (
            <div
              className={`rounded-md px-3 py-2 text-sm ${
                result.passed
                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                  : 'bg-destructive/10 text-destructive'
              }`}
            >
              <p className="font-medium">{result.message}</p>
            </div>
          )}

          {/* Expired state */}
          {isExpired && (
            <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" />
              Challenge expired. Your session may be restricted.
            </div>
          )}

          {/* Soft challenge: personal question */}
          {isSoft && !result && !isExpired && (
            <>
              <p className="text-sm text-muted-foreground">
                To confirm your identity, please answer this question:
              </p>
              <p className="font-medium">{challenge.question}</p>
              <input
                ref={inputRef}
                type="text"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Your answer..."
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <Button onClick={handleSubmit} disabled={!answer.trim()} className="w-full">
                Submit Answer
              </Button>
            </>
          )}

          {/* Hard challenge: choose method */}
          {!isSoft && !result && !isExpired && (
            <>
              <p className="text-sm text-muted-foreground">
                Suspicious activity detected. Please verify your identity using one of the following methods:
              </p>

              {!selectedMethod && (
                <div className="space-y-2">
                  {challenge.methods?.includes('secret_word') && (
                    <Button
                      variant="outline"
                      className="w-full justify-start gap-2"
                      onClick={() => setSelectedMethod('secret_word')}
                    >
                      <Lock className="h-4 w-4" />
                      Secret word / event
                    </Button>
                  )}
                  {challenge.methods?.includes('voice_match') && (
                    <Button
                      variant="outline"
                      className="w-full justify-start gap-2 opacity-50"
                      disabled
                    >
                      <Shield className="h-4 w-4" />
                      Voice verification (use Settings page)
                    </Button>
                  )}
                </div>
              )}

              {selectedMethod === 'secret_word' && (
                <div className="space-y-3">
                  <p className="text-sm font-medium">Enter your secret word or event:</p>
                  <input
                    ref={inputRef}
                    type="password"
                    value={secretValue}
                    onChange={(e) => setSecretValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Secret word..."
                    className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => setSelectedMethod(null)}
                    >
                      Back
                    </Button>
                    <Button
                      className="flex-1"
                      onClick={handleSubmit}
                      disabled={!secretValue.trim()}
                    >
                      Verify
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Dismiss button for completed challenges */}
          {(result || isExpired) && (
            <Button
              variant={result?.passed ? 'default' : 'outline'}
              onClick={onDismiss}
              className="w-full"
            >
              {result?.passed ? 'Continue chatting' : 'Close'}
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface LockoutScreenProps {
  message: string;
  onReauth: () => void;
}

export function LockoutScreen({ message, onReauth }: LockoutScreenProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md">
      <Card className="mx-4 w-full max-w-sm text-center shadow-2xl">
        <CardContent className="space-y-4 pt-8">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
            <Lock className="h-8 w-8 text-destructive" />
          </div>
          <h2 className="text-lg font-bold">Session Locked</h2>
          <p className="text-sm text-muted-foreground">{message}</p>
          <Button onClick={onReauth} className="w-full">
            Verify Identity
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
