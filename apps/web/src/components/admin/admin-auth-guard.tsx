'use client';

import { useAdminAuth } from '@/lib/hooks/use-admin-auth';
import { AdminSidebar } from '@/components/admin/admin-sidebar';
import { AdminTopBar } from '@/components/admin/admin-top-bar';
import { Loader2 } from 'lucide-react';

export function AdminAuthGuard({ children }: { children: React.ReactNode }) {
  const { loading, authenticated, username, logout } = useAdminAuth();

  if (loading || !authenticated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <AdminSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <AdminTopBar username={username} onLogout={logout} />
        <main className="flex-1 overflow-y-auto bg-background">{children}</main>
      </div>
    </div>
  );
}
