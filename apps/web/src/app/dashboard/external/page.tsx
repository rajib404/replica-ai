'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Zap,
  RefreshCw,
  DollarSign,
  Activity,
  Brain,
  Shield,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { ExternalProviderCard } from '@/components/dashboard/external-provider-card';
import { AddProviderDialog } from '@/components/dashboard/add-provider-dialog';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

interface ProviderConfig {
  id: string;
  owner_id: string;
  provider: string;
  model_name: string | null;
  monthly_budget_usd: number;
  daily_budget_usd: number;
  spent_this_month_usd: number;
  is_active: boolean;
  auto_learn: boolean;
  created_at: string;
  updated_at: string;
}

interface ConfigListResponse {
  configs: ProviderConfig[];
  total: number;
}

interface UsageLogEntry {
  id: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  was_sanitized: boolean;
  created_at: string;
}

interface UsageSummary {
  total_cost_usd: number;
  total_queries: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  budget_remaining_monthly: number;
  budget_pct_used: number;
  logs: UsageLogEntry[];
}

export default function ExternalAIPage() {
  const [configs, setConfigs] = useState<ProviderConfig[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [configData, usageData] = await Promise.all([
        api.get<ConfigListResponse>('/api/external/config'),
        api.get<UsageSummary>('/api/external/usage'),
      ]);
      setConfigs(configData.configs);
      setUsage(usageData);
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to load external AI data');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleToggle(configId: string, active: boolean) {
    try {
      await api.put(`/api/external/config/${configId}`, { is_active: active });
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleToggleLearn(configId: string, autoLearn: boolean) {
    try {
      await api.put(`/api/external/config/${configId}`, { auto_learn: autoLearn });
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleDelete(configId: string) {
    try {
      await api.delete(`/api/external/config/${configId}`);
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Zap className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">External AI</h1>
            <p className="text-sm text-muted-foreground">
              Connect external LLM providers for enhanced capabilities.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
            <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </Button>
          <AddProviderDialog onAdded={fetchData} />
        </div>
      </div>

      {/* Privacy notice */}
      <div className="flex items-start gap-3 rounded-lg border bg-muted/50 p-4">
        <Shield className="mt-0.5 h-5 w-5 text-primary shrink-0" />
        <div className="text-sm">
          <p className="font-medium">Privacy Firewall Active</p>
          <p className="text-muted-foreground">
            All outgoing prompts are automatically sanitized to remove personal data
            (emails, phone numbers, names, etc.) before being sent to external providers.
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Summary cards */}
      {usage && (
        <div className="grid gap-4 sm:grid-cols-4">
          <Card>
            <CardContent className="p-4 text-center">
              <DollarSign className="mx-auto mb-1 h-5 w-5 text-muted-foreground" />
              <p className="text-2xl font-bold">${usage.total_cost_usd.toFixed(2)}</p>
              <p className="text-xs text-muted-foreground">Total Spent</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <Activity className="mx-auto mb-1 h-5 w-5 text-muted-foreground" />
              <p className="text-2xl font-bold">{usage.total_queries}</p>
              <p className="text-xs text-muted-foreground">Total Queries</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <DollarSign className="mx-auto mb-1 h-5 w-5 text-muted-foreground" />
              <p className="text-2xl font-bold">${usage.budget_remaining_monthly.toFixed(2)}</p>
              <p className="text-xs text-muted-foreground">Budget Remaining</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <Brain className="mx-auto mb-1 h-5 w-5 text-muted-foreground" />
              <p className="text-2xl font-bold">
                {(usage.total_prompt_tokens + usage.total_completion_tokens).toLocaleString()}
              </p>
              <p className="text-xs text-muted-foreground">Total Tokens</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Budget warning */}
      {usage && usage.budget_pct_used >= 80 && (
        <div className={cn(
          'flex items-center gap-2 rounded-md border p-3 text-sm',
          usage.budget_pct_used >= 100
            ? 'border-destructive/50 bg-destructive/10 text-destructive'
            : 'border-orange-500/50 bg-orange-500/10 text-orange-700',
        )}>
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {usage.budget_pct_used >= 100
            ? 'Monthly budget exhausted. External queries are disabled until next month.'
            : `Budget warning: ${usage.budget_pct_used.toFixed(0)}% of monthly budget used.`}
        </div>
      )}

      {/* Provider cards */}
      {loading && configs.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-muted-foreground">
          Loading providers...
        </div>
      ) : configs.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
          <Zap className="h-8 w-8" />
          <p>No external providers configured.</p>
          <p className="text-xs">Click &quot;Add Provider&quot; to connect one.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {configs.map((config) => (
            <ExternalProviderCard
              key={config.id}
              config={config}
              onToggle={handleToggle}
              onToggleLearn={handleToggleLearn}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <Separator />

      {/* Usage log */}
      {usage && usage.logs.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Recent Usage</h2>
          <div className="space-y-2">
            {usage.logs.map((log) => (
              <Card key={log.id}>
                <CardContent className="flex items-center justify-between p-3">
                  <div className="flex items-center gap-3">
                    <Badge
                      variant="outline"
                      className="text-xs capitalize"
                    >
                      {log.provider}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {log.prompt_tokens + log.completion_tokens} tokens
                    </span>
                    {log.was_sanitized && (
                      <Badge variant="secondary" className="text-[10px]">
                        <Shield className="mr-1 h-2.5 w-2.5" />
                        Sanitized
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="font-medium">${log.cost_usd.toFixed(4)}</span>
                    <span>
                      {new Date(log.created_at).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
