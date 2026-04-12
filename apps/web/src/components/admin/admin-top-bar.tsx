'use client';

import { ShieldAlert, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface AdminTopBarProps {
  username: string | null;
  onLogout: () => void;
}

export function AdminTopBar({ username, onLogout }: AdminTopBarProps) {
  const env = process.env.NODE_ENV === 'production' ? 'PROD' : 'DEV';

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-4">
      <div className="flex items-center gap-3">
        <ShieldAlert className="h-5 w-5 text-primary" />
        <span className="font-medium">Admin Console</span>
        <Badge variant={env === 'PROD' ? 'destructive' : 'secondary'} className="text-[10px]">
          {env}
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        {username && (
          <span className="hidden text-sm text-muted-foreground sm:inline">
            Signed in as <span className="font-medium text-foreground">{username}</span>
          </span>
        )}
        <Button variant="ghost" size="sm" onClick={onLogout}>
          <LogOut className="mr-2 h-4 w-4" />
          Logout
        </Button>
      </div>
    </header>
  );
}
