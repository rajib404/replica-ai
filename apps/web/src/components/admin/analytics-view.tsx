'use client';

import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { adminApi } from '@/lib/admin/api';
import type {
  TimeSeriesPoint,
  KnowledgeTypeBucket,
  ExternalLLMUsagePoint,
  StorageProjectionPoint,
} from '@/lib/admin/types';
import { toast } from 'sonner';

const DauChart = dynamic(() => import('@/components/admin/charts/dau-chart'), { ssr: false });
const MessageVolumeChart = dynamic(() => import('@/components/admin/charts/message-volume-chart'), {
  ssr: false,
});
const KnowledgeRateChart = dynamic(
  () => import('@/components/admin/charts/knowledge-rate-chart'),
  { ssr: false },
);
const KnowledgeTypesChart = dynamic(
  () => import('@/components/admin/charts/knowledge-types-chart'),
  { ssr: false },
);
const ExternalLLMChart = dynamic(() => import('@/components/admin/charts/external-llm-chart'), {
  ssr: false,
});
const StorageProjectionChart = dynamic(
  () => import('@/components/admin/charts/storage-projection-chart'),
  { ssr: false },
);

interface ChartCardProps {
  title: string;
  loading: boolean;
  children: React.ReactNode;
}

function ChartCard({ title, loading, children }: ChartCardProps) {
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold">{title}</h3>
      {loading ? <Skeleton className="h-[250px] w-full" /> : children}
    </div>
  );
}

export function AnalyticsView() {
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [dau, setDau] = useState<TimeSeriesPoint[]>([]);
  const [messages, setMessages] = useState<TimeSeriesPoint[]>([]);
  const [knowledgeRate, setKnowledgeRate] = useState<TimeSeriesPoint[]>([]);
  const [knowledgeTypes, setKnowledgeTypes] = useState<KnowledgeTypeBucket[]>([]);
  const [externalLLM, setExternalLLM] = useState<ExternalLLMUsagePoint[]>([]);
  const [storage, setStorage] = useState<StorageProjectionPoint[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [dauR, msgR, kRateR, kTypesR, llmR, storR] = await Promise.all([
        adminApi.get<TimeSeriesPoint[]>('/analytics/dau', { params: { days } }),
        adminApi.get<TimeSeriesPoint[]>('/analytics/messages', { params: { days } }),
        adminApi.get<TimeSeriesPoint[]>('/analytics/knowledge-rate', { params: { days } }),
        adminApi.get<KnowledgeTypeBucket[]>('/analytics/knowledge-types'),
        adminApi.get<ExternalLLMUsagePoint[]>('/analytics/external-llm', { params: { days } }),
        adminApi.get<StorageProjectionPoint[]>('/analytics/storage', {
          params: { days, project_days: 90 },
        }),
      ]);
      setDau(dauR);
      setMessages(msgR);
      setKnowledgeRate(kRateR);
      setKnowledgeTypes(kTypesR);
      setExternalLLM(llmR);
      setStorage(storR);
    } catch {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-sm text-muted-foreground">Usage trends across the system</p>
        </div>
        <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Daily Active Users" loading={loading}>
          <DauChart data={dau} />
        </ChartCard>
        <ChartCard title="Message Volume" loading={loading}>
          <MessageVolumeChart data={messages} />
        </ChartCard>
        <ChartCard title="Knowledge Ingestion" loading={loading}>
          <KnowledgeRateChart data={knowledgeRate} />
        </ChartCard>
        <ChartCard title="Knowledge Types" loading={loading}>
          <KnowledgeTypesChart data={knowledgeTypes} />
        </ChartCard>
        <ChartCard title="External LLM Cost" loading={loading}>
          <ExternalLLMChart data={externalLLM} />
        </ChartCard>
        <ChartCard title="Storage Projection" loading={loading}>
          <StorageProjectionChart data={storage} />
        </ChartCard>
      </div>
    </div>
  );
}
