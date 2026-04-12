'use client';

import { useState } from 'react';
import { Clock, AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { AccessRule, LegacyConfig } from '@replica-ai/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

const TRIGGER_OPTIONS = [
  { value: 'manual', label: 'Manual', description: 'Activate legacy mode manually at any time.' },
  { value: 'inactivity', label: 'Inactivity', description: 'Auto-activate after N days of inactivity.' },
  { value: 'trusted_person', label: 'Trusted Person', description: 'A trusted person can trigger activation.' },
] as const;

interface LegacyConfigPanelProps {
  config: LegacyConfig | null;
  rules: AccessRule[];
  onUpdated: () => void;
}

export function LegacyConfigPanel({ config, rules, onUpdated }: LegacyConfigPanelProps) {
  const [triggerType, setTriggerType] = useState(config?.triggerType ?? 'manual');
  const [inactivityDays, setInactivityDays] = useState(config?.inactivityDays ?? 365);
  const [trustedRuleId, setTrustedRuleId] = useState(config?.trustedPersonRuleId ?? '');
  const [saving, setSaving] = useState(false);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  async function handleSave() {
    setError('');
    setSuccess('');
    setSaving(true);
    try {
      await api.put('/api/access/legacy/configure', {
        trigger_type: triggerType,
        inactivity_days: inactivityDays,
        trusted_person_rule_id: trustedRuleId || null,
      });
      setSuccess('Legacy configuration saved.');
      onUpdated();
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to save configuration');
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleActivate() {
    setError('');
    setSuccess('');
    setActivating(true);
    try {
      const result = await api.post<{ activated: boolean; message: string }>(
        '/api/access/legacy/activate',
      );
      if (result.activated) {
        setSuccess(result.message);
        onUpdated();
      } else {
        setError(result.message);
      }
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to activate legacy mode');
      }
    } finally {
      setActivating(false);
    }
  }

  const isActive = config?.isActive ?? false;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <Clock className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Legacy Mode</CardTitle>
        </div>
        <Badge
          className={
            isActive
              ? 'bg-green-500/15 text-green-700 border-green-500/25'
              : 'bg-muted text-muted-foreground'
          }
        >
          {isActive ? 'Active' : 'Inactive'}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {isActive ? (
          <div className="flex items-center gap-2 rounded-md border border-green-500/25 bg-green-500/10 p-3">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <p className="text-sm text-green-700">
              Legacy mode is active.
              {config?.activatedAt && (
                <span> Activated on {new Date(config.activatedAt).toLocaleDateString()}.</span>
              )}
            </p>
          </div>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Legacy mode allows your Replica to continue serving family members even if you are no longer able to manage it.
            </p>

            <div className="space-y-2">
              <Label>Trigger Type</Label>
              <div className="grid gap-2">
                {TRIGGER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTriggerType(opt.value)}
                    className={`flex flex-col items-start rounded-md border px-4 py-2.5 text-left transition-colors ${
                      triggerType === opt.value
                        ? 'border-primary bg-primary/5'
                        : 'border-input hover:bg-accent'
                    }`}
                  >
                    <span className="text-sm font-medium">{opt.label}</span>
                    <span className="text-xs text-muted-foreground">{opt.description}</span>
                  </button>
                ))}
              </div>
            </div>

            {triggerType === 'inactivity' && (
              <div className="space-y-2">
                <Label htmlFor="inactivity-days">Inactivity Threshold (days)</Label>
                <Input
                  id="inactivity-days"
                  type="number"
                  min={30}
                  max={3650}
                  value={inactivityDays}
                  onChange={(e) => setInactivityDays(Number(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">
                  Legacy mode will activate after {inactivityDays} days without activity.
                </p>
              </div>
            )}

            {triggerType === 'trusted_person' && (
              <div className="space-y-2">
                <Label>Trusted Person</Label>
                {rules.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Create an access rule first, then assign a trusted person.
                  </p>
                ) : (
                  <div className="grid gap-1.5">
                    {rules.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => setTrustedRuleId(r.id)}
                        className={`flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                          trustedRuleId === r.id
                            ? 'border-primary bg-primary/5'
                            : 'border-input hover:bg-accent'
                        }`}
                      >
                        <span>{r.granteeName}</span>
                        {r.granteeRelation && (
                          <span className="text-xs text-muted-foreground capitalize">
                            {r.granteeRelation.replace('_', ' ')}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-sm text-destructive">
                <AlertTriangle className="h-4 w-4" />
                {error}
              </div>
            )}
            {success && (
              <div className="flex items-center gap-2 rounded-md border border-green-500/25 bg-green-500/10 p-2 text-sm text-green-700">
                <CheckCircle2 className="h-4 w-4" />
                {success}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <Button onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save Configuration'}
              </Button>
              {config && (
                <Button variant="outline" onClick={handleActivate} disabled={activating}>
                  {activating ? 'Activating...' : 'Activate Now'}
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
