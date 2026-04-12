'use client';

import { useCallback, useEffect, useState } from 'react';

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
  prompt(): Promise<void>;
}

const DISMISS_KEY = 'pwa-install-dismissed-at';
const DISMISS_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function isCooldownActive(): boolean {
  if (typeof window === 'undefined') return true;
  const raw = window.localStorage.getItem(DISMISS_KEY);
  if (!raw) return false;
  const ts = Number(raw);
  if (Number.isNaN(ts)) return false;
  return Date.now() - ts < DISMISS_COOLDOWN_MS;
}

export function useInstallPrompt() {
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    setDismissed(isCooldownActive());

    // Detect already-installed display mode.
    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      // iOS Safari
      // @ts-expect-error — non-standard iOS property
      window.navigator.standalone === true;
    if (standalone) setInstalled(true);

    const handler = (e: Event) => {
      e.preventDefault();
      setEvent(e as BeforeInstallPromptEvent);
    };
    const installedHandler = () => {
      setInstalled(true);
      setEvent(null);
    };

    window.addEventListener('beforeinstallprompt', handler);
    window.addEventListener('appinstalled', installedHandler);
    return () => {
      window.removeEventListener('beforeinstallprompt', handler);
      window.removeEventListener('appinstalled', installedHandler);
    };
  }, []);

  const promptInstall = useCallback(async () => {
    if (!event) return null;
    await event.prompt();
    const choice = await event.userChoice;
    setEvent(null);
    if (choice.outcome === 'dismissed') {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
      setDismissed(true);
    }
    return choice.outcome;
  }, [event]);

  const dismiss = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
    }
    setDismissed(true);
  }, []);

  return {
    canInstall: !!event && !installed && !dismissed,
    promptInstall,
    dismiss,
    installed,
  };
}
