'use client';

import { Shield, Brain, Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface StepWelcomeProps {
  onNext: () => void;
}

export function StepWelcome({ onNext }: StepWelcomeProps) {
  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <h2 className="text-2xl font-bold">Welcome to Replica AI</h2>
        <p className="text-muted-foreground">
          Your personal AI that remembers everything about you &mdash; your stories, your
          preferences, your world.
        </p>
      </div>

      <div className="space-y-4">
        <div className="flex gap-3 rounded-lg border p-4">
          <Brain className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <p className="font-medium">Your Digital Twin</p>
            <p className="text-sm text-muted-foreground">
              Replica AI learns from the knowledge you share — text, voice, documents — and builds
              a personal model that thinks like you.
            </p>
          </div>
        </div>

        <div className="flex gap-3 rounded-lg border p-4">
          <Lock className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <p className="font-medium">You Own Your Data</p>
            <p className="text-sm text-muted-foreground">
              Everything stays on your devices or your chosen cloud. No training on your data, no
              selling to third parties. Ever.
            </p>
          </div>
        </div>

        <div className="flex gap-3 rounded-lg border p-4">
          <Shield className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <p className="font-medium">Family Access Control</p>
            <p className="text-sm text-muted-foreground">
              Grant family members access with custom verification — a secret word, a shared memory,
              voice or face recognition.
            </p>
          </div>
        </div>
      </div>

      <Button className="w-full" size="lg" onClick={onNext}>
        Get Started
      </Button>
    </div>
  );
}
