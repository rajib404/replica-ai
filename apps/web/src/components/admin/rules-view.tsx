'use client';

import { useEffect, useState, useCallback } from 'react';
import { Plus, Pencil, Trash2, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RuleFormDialog } from '@/components/admin/rule-form-dialog';
import { adminApi, ApiError } from '@/lib/admin/api';
import type { SystemRuleResponse, SystemConfigResponse, SystemConfigUpdate } from '@/lib/admin/types';
import { toast } from 'sonner';

export function RulesView() {
  const [rules, setRules] = useState<SystemRuleResponse[] | null>(null);
  const [config, setConfig] = useState<SystemConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<SystemRuleResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesResult, configResult] = await Promise.all([
        adminApi.get<SystemRuleResponse[]>('/rules'),
        adminApi.get<SystemConfigResponse>('/config'),
      ]);
      setRules(rulesResult);
      setConfig(configResult);
    } catch {
      toast.error('Failed to load rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleNew = () => {
    setEditingRule(null);
    setDialogOpen(true);
  };

  const handleEdit = (rule: SystemRuleResponse) => {
    setEditingRule(rule);
    setDialogOpen(true);
  };

  const handleDelete = async (rule: SystemRuleResponse) => {
    if (!confirm(`Delete rule "${rule.name}"?`)) return;
    try {
      await adminApi.delete(`/rules/${rule.id}`);
      toast.success('Rule deleted');
      load();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error('Failed to delete rule');
      }
    }
  };

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-2xl font-bold">Predefined Rules</h1>
        <p className="text-sm text-muted-foreground">
          Manage default replica configurations and global limits
        </p>
      </div>

      <Tabs defaultValue="rules">
        <TabsList>
          <TabsTrigger value="rules">Rules</TabsTrigger>
          <TabsTrigger value="config">System Config</TabsTrigger>
        </TabsList>

        <TabsContent value="rules" className="space-y-4">
          <div className="flex items-center justify-end">
            <Button onClick={handleNew}>
              <Plus className="mr-2 h-4 w-4" />
              New Rule
            </Button>
          </div>

          <div className="rounded-md border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Default</TableHead>
                  <TableHead>Base Model</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-32 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 4 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 5 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : rules && rules.length > 0 ? (
                  rules.map((rule) => (
                    <TableRow key={rule.id}>
                      <TableCell className="font-medium">
                        {rule.name}
                        {rule.description && (
                          <div className="text-xs text-muted-foreground">{rule.description}</div>
                        )}
                      </TableCell>
                      <TableCell>
                        {rule.is_default ? (
                          <Badge>
                            <Star className="mr-1 h-3 w-3" />
                            Default
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{rule.base_model ?? '—'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(rule.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => handleEdit(rule)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleDelete(rule)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      No rules defined
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="config">
          <SystemConfigForm config={config} rules={rules} onSaved={load} />
        </TabsContent>
      </Tabs>

      <RuleFormDialog
        open={dialogOpen}
        rule={editingRule}
        onClose={() => setDialogOpen(false)}
        onSaved={load}
      />
    </div>
  );
}

interface SystemConfigFormProps {
  config: SystemConfigResponse | null;
  rules: SystemRuleResponse[] | null;
  onSaved: () => void;
}

function SystemConfigForm({ config, rules, onSaved }: SystemConfigFormProps) {
  const [defaultRuleId, setDefaultRuleId] = useState('');
  const [defaultBaseModel, setDefaultBaseModel] = useState('');
  const [globalRateLimit, setGlobalRateLimit] = useState('');
  const [globalFileSizeMb, setGlobalFileSizeMb] = useState('');
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (config) {
      setDefaultRuleId(config.default_rule_id ?? '');
      setDefaultBaseModel(config.default_base_model ?? '');
      setGlobalRateLimit(config.global_rate_limit_per_minute?.toString() ?? '');
      setGlobalFileSizeMb(
        config.global_file_size_limit_bytes
          ? Math.round(config.global_file_size_limit_bytes / 1_048_576).toString()
          : '',
      );
      setMaintenanceMode(config.maintenance_mode);
    }
  }, [config]);

  const handleSave = async () => {
    setSubmitting(true);
    const payload: SystemConfigUpdate = {
      default_rule_id: defaultRuleId || null,
      default_base_model: defaultBaseModel || null,
      global_rate_limit_per_minute: globalRateLimit ? Number(globalRateLimit) : null,
      global_file_size_limit_bytes: globalFileSizeMb ? Number(globalFileSizeMb) * 1_048_576 : null,
      maintenance_mode: maintenanceMode,
    };
    try {
      await adminApi.put('/config', payload);
      toast.success('Config saved');
      onSaved();
    } catch {
      toast.error('Failed to save config');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4 rounded-md border bg-card p-6">
      <div className="space-y-2">
        <label className="text-sm font-medium">Default Rule</label>
        <Select value={defaultRuleId || 'none'} onValueChange={(v) => setDefaultRuleId(v === 'none' ? '' : v)}>
          <SelectTrigger>
            <SelectValue placeholder="Select rule" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">— None —</SelectItem>
            {rules?.map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Default Base Model</label>
        <Input
          value={defaultBaseModel}
          onChange={(e) => setDefaultBaseModel(e.target.value)}
          placeholder="llama3.2:3b"
        />
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Global Rate Limit (per minute)</label>
        <Input
          type="number"
          value={globalRateLimit}
          onChange={(e) => setGlobalRateLimit(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Global File Size Limit (MB)</label>
        <Input
          type="number"
          value={globalFileSizeMb}
          onChange={(e) => setGlobalFileSizeMb(e.target.value)}
        />
      </div>

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <div className="text-sm font-medium">Maintenance mode</div>
          <div className="text-xs text-muted-foreground">
            Disable user-facing endpoints temporarily
          </div>
        </div>
        <Switch checked={maintenanceMode} onCheckedChange={setMaintenanceMode} />
      </div>

      <Button onClick={handleSave} disabled={submitting}>
        {submitting ? 'Saving...' : 'Save changes'}
      </Button>
    </div>
  );
}
