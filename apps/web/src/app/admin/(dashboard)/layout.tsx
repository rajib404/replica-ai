import { AdminAuthGuard } from '@/components/admin/admin-auth-guard';

export default function AdminDashboardLayout({ children }: { children: React.ReactNode }) {
  return <AdminAuthGuard>{children}</AdminAuthGuard>;
}
