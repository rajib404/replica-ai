'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { StepWelcome } from '@/components/setup/step-welcome';
import { StepAboutYou } from '@/components/setup/step-about-you';
import { StepSecurity } from '@/components/setup/step-security';
import { StepComplete } from '@/components/setup/step-complete';

export interface SetupData {
  name: string;
  email: string;
  preferredLanguage: string;
  verificationMethod: 'secret_word' | 'secret_event';
  secretValue: string;
}

export interface SetupResult {
  ownerId: string;
  accessToken: string;
  refreshToken: string;
  connectUrl: string;
  qrCodeBase64: string;
}

const STEPS = ['Welcome', 'About You', 'Security', 'Complete'] as const;

export function SetupWizard() {
  const [step, setStep] = useState(0);
  const [data, setData] = useState<SetupData>({
    name: '',
    email: '',
    preferredLanguage: 'en',
    verificationMethod: 'secret_word',
    secretValue: '',
  });
  const [result, setResult] = useState<SetupResult | null>(null);

  const updateData = (partial: Partial<SetupData>) => {
    setData((prev) => ({ ...prev, ...partial }));
  };

  return (
    <Card className="w-full max-w-lg">
      {/* Step indicator */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                i < step
                  ? 'bg-primary text-primary-foreground'
                  : i === step
                    ? 'border-2 border-primary text-primary'
                    : 'border border-muted-foreground/30 text-muted-foreground'
              }`}
            >
              {i < step ? '\u2713' : i + 1}
            </div>
            <span
              className={`hidden text-xs sm:inline ${
                i === step ? 'font-medium text-foreground' : 'text-muted-foreground'
              }`}
            >
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <div className="mx-1 hidden h-px w-6 bg-border sm:block" />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="p-6">
        {step === 0 && <StepWelcome onNext={() => setStep(1)} />}
        {step === 1 && (
          <StepAboutYou
            data={data}
            onChange={updateData}
            onBack={() => setStep(0)}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <StepSecurity
            data={data}
            onChange={updateData}
            onBack={() => setStep(1)}
            onNext={(setupResult) => {
              setResult(setupResult);
              setStep(3);
            }}
          />
        )}
        {step === 3 && result && <StepComplete result={result} />}
      </div>
    </Card>
  );
}
