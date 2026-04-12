'use client';

import { useCallback, useEffect, useState } from 'react';
import { Users, RefreshCw } from 'lucide-react';
import type { AccessRule, LegacyConfig } from '@replica-ai/shared';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { RuleCard } from '@/components/dashboard/rule-card';
import { CreateRuleDialog } from '@/components/dashboard/create-rule-dialog';
import { LegacyConfigPanel } from '@/components/dashboard/legacy-config-panel';
import { FamilySessionsPanel } from '@/components/dashboard/family-sessions-panel';
import { api } from '@/lib/api';

interface RuleListResponse {
  rules: AccessRule[];
  total: number;
}

interface Template {
  name: string;
  label: string;
  description: string;
  config: {
    grantee_name: string;
    grantee_relation: string | null;
    access_level: string;
    verification_method: string;
    topic_restrictions: { allowed: string[]; blocked: string[] } | null;
    template_name: string | null;
  };
}

interface TemplateListResponse {
  templates: Template[];
}

export default function FamilyAccessPage() {
  const [rules, setRules] = useState<AccessRule[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [legacyConfig, setLegacyConfig] = useState<LegacyConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [rulesData, templatesData, legacyData] = await Promise.all([
        api.get<RuleListResponse>('/api/access/rules'),
        api.get<TemplateListResponse>('/api/access/templates'),
        api.get<LegacyConfig | null>('/api/access/legacy'),
      ]);
      setRules(rulesData.rules);
      setTemplates(templatesData.templates);
      setLegacyConfig(legacyData);
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to load family access data');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleToggle(ruleId: string, active: boolean) {
    try {
      await api.put(`/api/access/rules/${ruleId}`, { is_active: active });
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      }
    }
  }

  async function handleDelete(ruleId: string) {
    try {
      await api.delete(`/api/access/rules/${ruleId}`);
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      }
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Users className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Family Access</h1>
            <p className="text-sm text-muted-foreground">
              Manage who can interact with your Replica.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <CreateRuleDialog templates={templates} onCreated={fetchData} />
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && rules.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-muted-foreground">
          Loading access rules...
        </div>
      ) : rules.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
          <Users className="h-8 w-8" />
          <p>No access rules yet.</p>
          <p className="text-xs">Click &quot;Add Access Rule&quot; to create one.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {rules.map((rule) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <Separator />

      <FamilySessionsPanel />

      <Separator />

      <LegacyConfigPanel
        config={legacyConfig}
        rules={rules.filter((r) => r.isActive)}
        onUpdated={fetchData}
      />
    </div>
  );
}
