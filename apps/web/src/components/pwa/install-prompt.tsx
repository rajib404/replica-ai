'use client';

import { Download, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { useInstallPrompt } from '@/lib/hooks/use-install-prompt';

export function InstallPrompt() {
  const t = useTranslations('pwa');
  const { canInstall, promptInstall, dismiss } = useInstallPrompt();

  if (!canInstall) return null;

  return (
    <div className="desktop:hidden fixed inset-x-3 bottom-20 z-40 mx-auto max-w-sm rounded-xl border bg-card p-3 shadow-lg">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Download className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium">{t('install')}</p>
          <p className="text-xs text-muted-foreground">{t('installPrompt')}</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          onClick={dismiss}
          aria-label={t('notNow')}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="mt-3 flex gap-2">
        <Button size="sm" className="flex-1" onClick={() => promptInstall()}>
          {t('install')}
        </Button>
        <Button size="sm" variant="ghost" className="flex-1" onClick={dismiss}>
          {t('notNow')}
        </Button>
      </div>
    </div>
  );
}
