import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  subtext?: string;
  className?: string;
}

export function StatCard({ label, value, icon: Icon, subtext, className }: StatCardProps) {
  return (
    <div className={cn('rounded-lg border bg-card p-4 shadow-sm', className)}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums">{value}</div>
      {subtext && <div className="mt-1 text-xs text-muted-foreground">{subtext}</div>}
    </div>
  );
}
