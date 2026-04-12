'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  MessageSquare,
  BookOpen,
  Users,
  Settings,
  Server,
  Brain,
  Sparkles,
  GraduationCap,
  Cpu,
  Shield,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Separator } from '@/components/ui/separator';
import { ThemeToggle } from '@/components/theme-toggle';

const NAV_ITEMS = [
  { href: '/dashboard/chat', label: 'Chat', icon: MessageSquare },
  { href: '/dashboard/knowledge', label: 'Knowledge', icon: BookOpen },
  { href: '/dashboard/personality', label: 'Personality', icon: Sparkles },
  { href: '/dashboard/learning', label: 'Self-Learning', icon: GraduationCap },
  { href: '/dashboard/training', label: 'Model Training', icon: Cpu },
  { href: '/dashboard/family', label: 'Family Access', icon: Users },
  { href: '/dashboard/security', label: 'Security', icon: Shield },
  { href: '/dashboard/settings', label: 'Settings', icon: Settings },
  { href: '/dashboard/models', label: 'Model Status', icon: Server },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-60 flex-col border-r bg-card">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <Brain className="h-4 w-4 text-primary-foreground" />
        </div>
        <span className="text-lg font-bold">Replica AI</span>
      </div>

      <Separator />

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-3">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <Separator />

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-xs text-muted-foreground">v0.1.0</span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
