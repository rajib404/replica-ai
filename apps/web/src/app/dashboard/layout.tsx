import { Sidebar } from '@/components/dashboard/sidebar';
import { TopBar } from '@/components/dashboard/top-bar';
import { BottomNav } from '@/components/dashboard/bottom-nav';
import { SystemStatus } from '@/components/dashboard/system-status';
import { OfflineBanner } from '@/components/pwa/offline-banner';
import { InstallPrompt } from '@/components/pwa/install-prompt';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden desktop:block">
        <Sidebar />
      </div>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <OfflineBanner />
        <main className="flex-1 overflow-y-auto pb-16 desktop:pb-0">{children}</main>
        <SystemStatus />
      </div>

      {/* Mobile bottom nav (replaces hamburger drawer) */}
      <BottomNav />
      <InstallPrompt />
    </div>
  );
}
