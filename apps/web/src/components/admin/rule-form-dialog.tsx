'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { adminApi, ApiError } from '@/lib/admin/api';
import type { SystemRuleResponse, SystemRuleCreate } from '@/lib/admin/types';
import { toast } from 'sonner';

interface RuleFormDialogProps {
  open: boolean;
  rule: SystemRuleResponse | null;
  onClose: () => void;
  onSaved: () => void;
}

export function RuleFormDialog({ open, rule, onClose, onSaved }: RuleFormDialogProps) {
  const isEdit = !!rule;
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [baseModel, setBaseModel] = useState('');
  const [perMinute, setPerMinute] = useState('');
  const [perHour, setPerHour] = useState('');
  const [perDay, setPerDay] = useState('');
  const [fileSizeMb, setFileSizeMb] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [personalityJson, setPersonalityJson] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setName(rule?.name ?? '');
      setDescription(rule?.description ?? '');
      setSystemPrompt(rule?.system_prompt ?? '');
      setBaseModel(rule?.base_model ?? '');
      setPerMinute(rule?.rate_limits?.per_minute?.toString() ?? '');
      setPerHour(rule?.rate_limits?.per_hour?.toString() ?? '');
      setPerDay(rule?.rate_limits?.per_day?.toString() ?? '');
      setFileSizeMb(
        rule?.file_size_limit_bytes
          ? Math.round(rule.file_size_limit_bytes / 1_048_576).toString()
          : '',
      );
      setIsDefault(rule?.is_default ?? false);
      setPersonalityJson(
        rule?.personality_baseline ? JSON.stringify(rule.personality_baseline, null, 2) : '',
      );
    }
  }, [open, rule]);

  const formatJson = () => {
    try {
      const parsed = JSON.parse(personalityJson);
      setPersonalityJson(JSON.stringify(parsed, null, 2));
    } catch {
      toast.error('Invalid JSON');
    }
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitting(true);

    let personalityBaseline = null;
    if (personalityJson.trim()) {
      try {
        personalityBaseline = JSON.parse(personalityJson);
      } catch {
        toast.error('Personality baseline JSON is invalid');
        setSubmitting(false);
        return;
      }
    }

    const payload: SystemRuleCreate = {
      name,
      description: description || null,
      system_prompt: systemPrompt || null,
      base_model: baseModel || null,
      personality_baseline: personalityBaseline,
      rate_limits: {
        per_minute: perMinute ? Number(perMinute) : null,
        per_hour: perHour ? Number(perHour) : null,
        per_day: perDay ? Number(perDay) : null,
      },
      file_size_limit_bytes: fileSizeMb ? Number(fileSizeMb) * 1_048_576 : null,
      is_default: isDefault,
    };

    try {
      if (isEdit && rule) {
        await adminApi.put(`/rules/${rule.id}`, payload);
        toast.success('Rule updated');
      } else {
        await adminApi.post('/rules', payload);
        toast.success('Rule created');
      }
      onSaved();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error('Failed to save rule');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Rule' : 'New Rule'}</DialogTitle>
          <DialogDescription>
            Configure a predefined rule for replica behavior and limits
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Description</label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">System Prompt</label>
            <Textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={4}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Base Model</label>
            <Input
              value={baseModel}
              onChange={(e) => setBaseModel(e.target.value)}
              placeholder="e.g., llama3.2:3b"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">Per minute</label>
              <Input
                type="number"
                value={perMinute}
                onChange={(e) => setPerMinute(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Per hour</label>
              <Input type="number" value={perHour} onChange={(e) => setPerHour(e.target.value)} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Per day</label>
              <Input type="number" value={perDay} onChange={(e) => setPerDay(e.target.value)} />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">File size limit (MB)</label>
            <Input
              type="number"
              value={fileSizeMb}
              onChange={(e) => setFileSizeMb(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Personality baseline (JSON)</label>
              <Button type="button" size="sm" variant="ghost" onClick={formatJson}>
                Format
              </Button>
            </div>
            <Textarea
              value={personalityJson}
              onChange={(e) => setPersonalityJson(e.target.value)}
              rows={5}
              className="font-mono text-xs"
              placeholder='{"tone": "friendly", ...}'
            />
          </div>

          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <div className="text-sm font-medium">Set as default</div>
              <div className="text-xs text-muted-foreground">
                Used for new replicas if no other rule is selected
              </div>
            </div>
            <Switch checked={isDefault} onCheckedChange={setIsDefault} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving...' : isEdit ? 'Save changes' : 'Create rule'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
