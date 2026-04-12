'use client';

import { useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';

const LOCALE_LABELS: Record<string, string> = {
  en: 'English',
  es: 'Espanol',
  ar: '\u0627\u0644\u0639\u0631\u0628\u064a\u0629',
  bn: '\u09ac\u09be\u0982\u09b2\u09be',
  hi: '\u0939\u093f\u0928\u094d\u0926\u0940',
  zh: '\u4e2d\u6587',
  fr: 'Francais',
};

const LOCALES = Object.keys(LOCALE_LABELS);

export function LanguageSwitcher() {
  const locale = useLocale();
  const router = useRouter();

  function setLocale(newLocale: string) {
    document.cookie = `locale=${newLocale};path=/;max-age=${60 * 60 * 24 * 365}`;
    router.refresh();
  }

  return (
    <div className="flex items-center gap-1">
      <Globe className="h-4 w-4 text-muted-foreground" />
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value)}
        className="rounded-md border border-input bg-background px-2 py-1 text-xs"
      >
        {LOCALES.map((loc) => (
          <option key={loc} value={loc}>
            {LOCALE_LABELS[loc]}
          </option>
        ))}
      </select>
    </div>
  );
}

export function LanguageSwitcherFull() {
  const locale = useLocale();
  const router = useRouter();

  function setLocale(newLocale: string) {
    document.cookie = `locale=${newLocale};path=/;max-age=${60 * 60 * 24 * 365}`;
    router.refresh();
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {LOCALES.map((loc) => (
        <Button
          key={loc}
          variant={locale === loc ? 'default' : 'outline'}
          size="sm"
          onClick={() => setLocale(loc)}
          className="justify-start"
        >
          {LOCALE_LABELS[loc]}
        </Button>
      ))}
    </div>
  );
}
