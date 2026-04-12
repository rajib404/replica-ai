'use client';

import { useEffect, useState } from 'react';
import { Loader2, WifiOff } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useOnlineStatus } from '@/lib/hooks/use-online-status';
import { cn } from '@/lib/utils';

export function OfflineBanner() {
  const t = useTranslations('pwa');
  const status = useOnlineStatus();
  const [queuedCount, setQueuedCount] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ count: number }>).detail;
      setQueuedCount(detail?.count ?? 0);
    };
    window.addEventListener('chat-queue-change', handler as EventListener);
    return () => window.removeEventListener('chat-queue-change', handler as EventListener);
  }, []);

  if (status === 'online') return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'sticky top-0 z-30 flex items-center justify-center gap-2 px-4 py-1.5 text-xs font-medium',
        status === 'offline'
          ? 'bg-red-500/15 text-red-600 dark:text-red-300'
          : 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
      )}
    >
      {status === 'offline' ? (
        <>
          <WifiOff className="h-3.5 w-3.5" />
          <span>{t('offline')}</span>
        </>
      ) : (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{t('reconnecting')}</span>
        </>
      )}
      {queuedCount > 0 && (
        <span className="ml-1 rounded-full bg-background/40 px-1.5 py-0.5 text-[10px]">
          {t('queuedMessages', { count: queuedCount })}
        </span>
      )}
    </div>
  );
}
