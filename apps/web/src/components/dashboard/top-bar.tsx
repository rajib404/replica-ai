'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LogOut, RefreshCw } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useOnlineStatus, type OnlineStatus } from '@/lib/hooks/use-online-status';

export function TopBar() {
  const router = useRouter();
  const [ownerName, setOwnerName] = useState('');
  const [signingOut, setSigningOut] = useState(false);
  const status = useOnlineStatus();

  useEffect(() => {
    setOwnerName(localStorage.getItem('owner_name') ?? 'Owner');
  }, []);

  async function handleSignOut() {
    setSigningOut(true);
    const refreshToken = api.getRefreshToken();
    try {
      if (refreshToken) {
        await api.post('/api/auth/logout', { refresh_token: refreshToken });
      }
    } catch {
      // Best-effort revoke — sign the user out locally regardless.
    } finally {
      api.clearTokens();
      localStorage.removeItem('owner_name');
      router.push('/login');
    }
  }

  const initials = ownerName
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  const statusColor: Record<OnlineStatus, string> = {
    online: 'bg-emerald-500',
    degraded: 'bg-amber-500',
    offline: 'bg-red-500',
  };

  const statusLabel: Record<OnlineStatus, string> = {
    online: 'All models online',
    degraded: 'Reconnecting...',
    offline: 'Offline',
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Avatar className="h-8 w-8">
            <AvatarFallback className="text-xs">{initials}</AvatarFallback>
          </Avatar>
          <span className="font-medium">{ownerName}</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Sync status */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw className={cn('h-3.5 w-3.5', status === 'degraded' && 'animate-spin')} />
          <span className="hidden sm:inline">{statusLabel[status]}</span>
        </div>

        {/* Status dot */}
        <div className="flex items-center gap-2">
          <div className={cn('h-2.5 w-2.5 rounded-full', statusColor[status])} />
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleSignOut}
          disabled={signingOut}
          title="Sign out"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
