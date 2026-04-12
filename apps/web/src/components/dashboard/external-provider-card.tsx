'use client';

import { useState } from 'react';
import {
  Trash2,
  Power,
  PowerOff,
  Brain,
  DollarSign,
  Activity,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google AI',
  custom: 'Custom',
};

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-green-500/15 text-green-700 border-green-500/25',
  anthropic: 'bg-orange-500/15 text-orange-700 border-orange-500/25',
  google: 'bg-blue-500/15 text-blue-700 border-blue-500/25',
  custom: 'bg-purple-500/15 text-purple-700 border-purple-500/25',
};

interface ProviderConfig {
  id: string;
  provider: string;
  model_name: string | null;
  monthly_budget_usd: number;
  daily_budget_usd: number;
  spent_this_month_usd: number;
  is_active: boolean;
  auto_learn: boolean;
}

interface ExternalProviderCardProps {
  config: ProviderConfig;
  onToggle: (id: string, active: boolean) => void;
  onToggleLearn: (id: string, autoLearn: boolean) => void;
  onDelete: (id: string) => void;
}

export function ExternalProviderCard({
  config,
  onToggle,
  onToggleLearn,
  onDelete,
}: ExternalProviderCardProps) {
  const budgetPct =
    config.monthly_budget_usd > 0
      ? (config.spent_this_month_usd / config.monthly_budget_usd) * 100
      : 0;
  const isOverBudget = budgetPct >= 100;
  const isWarning = budgetPct >= 80;

  return (
    <Card className={cn(!config.is_active && 'opacity-60')}>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">
            {PROVIDER_LABELS[config.provider] ?? config.provider}
          </CardTitle>
          <Badge className={cn('text-xs', PROVIDER_COLORS[config.provider] ?? '')}>
            {config.provider}
          </Badge>
        </div>
        <Badge variant={config.is_active ? 'default' : 'secondary'} className="text-xs">
          {config.is_active ? 'Active' : 'Disabled'}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {config.model_name && (
          <p className="text-xs text-muted-foreground font-mono">{config.model_name}</p>
        )}

        {/* Budget bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1 text-muted-foreground">
              <DollarSign className="h-3 w-3" />
              ${config.spent_this_month_usd.toFixed(2)} / ${config.monthly_budget_usd.toFixed(2)}
            </span>
            <span
              className={cn(
                'font-medium',
                isOverBudget
                  ? 'text-destructive'
                  : isWarning
                    ? 'text-orange-600'
                    : 'text-muted-foreground',
              )}
            >
              {budgetPct.toFixed(0)}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted">
            <div
              className={cn(
                'h-full rounded-full transition-all',
                isOverBudget
                  ? 'bg-destructive'
                  : isWarning
                    ? 'bg-orange-500'
                    : 'bg-primary',
              )}
              style={{ width: `${Math.min(budgetPct, 100)}%` }}
            />
          </div>
          {config.daily_budget_usd > 0 && (
            <p className="text-[10px] text-muted-foreground">
              Daily limit: ${config.daily_budget_usd.toFixed(2)}
            </p>
          )}
        </div>

        {/* Auto-learn badge */}
        {config.auto_learn && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Brain className="h-3 w-3" />
            Auto-learning enabled
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onToggle(config.id, !config.is_active)}
          >
            {config.is_active ? (
              <>
                <PowerOff className="mr-1.5 h-3.5 w-3.5" />
                Disable
              </>
            ) : (
              <>
                <Power className="mr-1.5 h-3.5 w-3.5" />
                Enable
              </>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onToggleLearn(config.id, !config.auto_learn)}
          >
            <Brain className="mr-1.5 h-3.5 w-3.5" />
            {config.auto_learn ? 'Stop Learning' : 'Auto-Learn'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onDelete(config.id)}>
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
