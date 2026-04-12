import { getRequestConfig } from 'next-intl/server';
import { cookies, headers } from 'next/headers';

export const locales = ['en', 'es', 'ar', 'bn', 'hi', 'zh', 'fr'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'en';

export default getRequestConfig(async () => {
  // Priority: cookie > Accept-Language header > default
  const cookieStore = await cookies();
  const localeCookie = cookieStore.get('locale')?.value;

  let locale: Locale = defaultLocale;

  if (localeCookie && locales.includes(localeCookie as Locale)) {
    locale = localeCookie as Locale;
  } else {
    const headerStore = await headers();
    const acceptLang = headerStore.get('accept-language') ?? '';
    const preferred = acceptLang
      .split(',')
      .map((part) => part.split(';')[0].trim().substring(0, 2).toLowerCase());
    const match = preferred.find((lang) => locales.includes(lang as Locale));
    if (match) {
      locale = match as Locale;
    }
  }

  return {
    locale,
    messages: (await import(`@/messages/${locale}.json`)).default,
  };
});
