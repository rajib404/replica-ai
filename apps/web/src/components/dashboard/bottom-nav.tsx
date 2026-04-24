'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import {
  MessageSquare,
  BookOpen,
  Archive,
  Sparkles,
  Users,
  MoreHorizontal,
  GraduationCap,
  Cpu,
  Shield,
  Settings,
  Server,
  Globe,
  Compass,
  CreditCard,
  LogOut,
} from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import { cn } from '@/lib/utils';
import { Separator } from '@/components/ui/separator';
import { ThemeToggle } from '@/components/theme-toggle';
import { api } from '@/lib/api';
import { useHaptic } from '@/lib/hooks/use-haptic';

const PRIMARY = [
  { href: '/dashboard/chat', label: 'Chat', icon: MessageSquare },
  { href: '/dashboard/knowledge', label: 'Knowledge', icon: BookOpen },
  { href: '/dashboard/assets', label: 'Assets', icon: Archive },
  { href: '/dashboard/personality', label: 'Personality', icon: Sparkles },
] as const;

const OVERFLOW = [
  { href: '/dashboard/family', label: 'Family', icon: Users },
  { href: '/dashboard/learning', label: 'Self-Learning', icon: GraduationCap },
  { href: '/dashboard/training', label: 'Model Training', icon: Cpu },
  { href: '/dashboard/security', label: 'Security', icon: Shield },
  { href: '/dashboard/settings', label: 'Settings', icon: Settings },
  { href: '/dashboard/models', label: 'Model Status', icon: Server },
  { href: '/dashboard/external', label: 'External AI', icon: Globe },
  { href: '/dashboard/browse', label: 'Browse', icon: Compass },
  { href: '/dashboard/billing', label: 'Billing', icon: CreditCard },
] as const;

export function BottomNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const haptic = useHaptic();

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + '/');
  // Highlight "More" if any overflow item is active.
  const moreActive = OVERFLOW.some((o) => isActive(o.href));

  function handleLogout() {
    api.clearTokens();
    setMoreOpen(false);
    window.location.href = '/';
  }

  return (
    <>
      <nav
        role="navigation"
        aria-label="Primary"
        className="desktop:hidden fixed inset-x-0 bottom-0 z-30 flex h-16 items-stretch border-t bg-card pb-[env(safe-area-inset-bottom)]"
      >
        {PRIMARY.map(({ href, label, icon: Icon }) => {
          const active = isActive(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              onClick={() => haptic.light()}
              className={cn(
                'flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors',
                active
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-5 w-5" />
              <span>{label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          aria-label="More"
          onClick={() => {
            haptic.light();
            setMoreOpen(true);
          }}
          className={cn(
            'flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors',
            moreActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <MoreHorizontal className="h-5 w-5" />
          <span>More</span>
        </button>
      </nav>

      <Dialog.Root open={moreOpen} onOpenChange={setMoreOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=open]:fade-in" />
          <Dialog.Content
            className="fixed inset-x-0 bottom-0 z-50 max-h-[80vh] overflow-y-auto rounded-t-2xl bg-card p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-xl data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom"
            aria-describedby={undefined}
          >
            <Dialog.Title className="sr-only">More navigation</Dialog.Title>
            <div className="mx-auto mb-4 h-1 w-12 rounded-full bg-muted" />
            <div className="grid grid-cols-2 gap-2">
              {OVERFLOW.map(({ href, label, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMoreOpen(false)}
                    className={cn(
                      'flex h-14 items-center gap-3 rounded-lg border px-3 text-sm font-medium transition-colors',
                      active
                        ? 'bg-accent text-accent-foreground'
                        : 'hover:bg-accent hover:text-accent-foreground',
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </Link>
                );
              })}
            </div>

            <Separator className="my-4" />

            <div className="flex items-center justify-between px-1">
              <span className="text-xs text-muted-foreground">Theme</span>
              <ThemeToggle />
            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-destructive/40 px-3 py-3 text-sm font-medium text-destructive hover:bg-destructive/10"
            >
              <LogOut className="h-4 w-4" />
              Log out
            </button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
