'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Copy, ExternalLink, QrCode } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { SetupResult } from '@/components/setup/setup-wizard';

interface StepCompleteProps {
  result: SetupResult;
}

export function StepComplete({ result }: StepCompleteProps) {
  const router = useRouter();
  const [copied, setCopied] = useState(false);

  async function copyLink() {
    await navigator.clipboard.writeText(result.connectUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Check className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-bold">You&apos;re All Set!</h2>
        <p className="text-sm text-muted-foreground">
          Your Replica has been created. Use the QR code or link below to connect other devices.
        </p>
      </div>

      {/* QR Code */}
      <div className="flex flex-col items-center gap-4">
        <div className="rounded-lg border bg-white p-4">
          {result.qrCodeBase64 ? (
            <img
              src={`data:image/png;base64,${result.qrCodeBase64}`}
              alt="Connection QR Code"
              className="h-48 w-48"
            />
          ) : (
            <div className="flex h-48 w-48 items-center justify-center">
              <QrCode className="h-12 w-12 text-muted-foreground" />
            </div>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground">
          Scan this QR code from another device to connect it to your Replica
        </p>
      </div>

      {/* Connection link */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Shareable Link</label>
        <div className="flex gap-2">
          <div className="flex-1 truncate rounded-md border bg-muted px-3 py-2 text-sm">
            {result.connectUrl}
          </div>
          <Button variant="outline" size="icon" onClick={copyLink}>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        <Button className="w-full" size="lg" onClick={() => router.push('/dashboard')}>
          Go to Dashboard
          <ExternalLink className="ml-2 h-4 w-4" />
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          Bookmark this page — you&apos;ll need the link to connect new devices later.
        </p>
      </div>
    </div>
  );
}
