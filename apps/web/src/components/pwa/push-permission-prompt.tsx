'use client';

import { useEffect, useState } from 'react';
import { Bell, BellOff, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { usePushSubscription } from '@/lib/hooks/use-push-subscription';

const DISMISS_KEY = 'pwa-push-prompt-dismissed-at';
const DISMISS_COOLDOWN_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

export function PushPermissionPrompt() {
  const t = useTranslations('pwa');
  const { supported, permission, subscription, loading, error, subscribe } = usePushSubscription();
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const raw = window.localStorage.getItem(DISMISS_KEY);
    if (!raw) {
      setDismissed(false);
      return;
    }
    const at = Number.parseInt(raw, 10);
    if (Number.isFinite(at) && Date.now() - at < DISMISS_COOLDOWN_MS) {
      setDismissed(true);
    } else {
      setDismissed(false);
    }
  }, []);

  function handleDismiss() {
    setDismissed(true);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
    }
  }

  async function handleEnable() {
    const sub = await subscribe();
    if (sub) {
      handleDismiss();
    }
  }

  if (!supported) return null;
  if (subscription) return null;
  if (permission === 'denied') {
    if (dismissed) return null;
    return (
      <div className="mx-auto mt-4 flex max-w-2xl items-center gap-3 rounded-lg border bg-card px-4 py-3 text-sm shadow-sm">
        <BellOff className="h-5 w-5 shrink-0 text-muted-foreground" />
        <p className="flex-1 text-muted-foreground">{t('pushBlocked')}</p>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss"
          className="rounded p-1 text-muted-foreground hover:bg-muted"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }
  if (dismissed) return null;

  return (
    <div className="mx-auto mt-4 flex max-w-2xl flex-col gap-3 rounded-lg border bg-card p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
          <Bell className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold">{t('enablePushNotifications')}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('enablePushDescription')}</p>
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss"
          className="rounded p-1 text-muted-foreground hover:bg-muted"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {error && (
        <p className="rounded bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={handleDismiss}
          className="rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted"
        >
          {t('notNow')}
        </button>
        <button
          type="button"
          onClick={handleEnable}
          disabled={loading}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? '...' : t('enableNotifications')}
        </button>
      </div>
    </div>
  );
}
