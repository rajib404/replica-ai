'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI', placeholder: 'sk-...' },
  { value: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-...' },
  { value: 'google', label: 'Google AI', placeholder: 'AIza...' },
  { value: 'custom', label: 'Custom', placeholder: 'API key' },
] as const;

interface AddProviderDialogProps {
  onAdded: () => void;
}

export function AddProviderDialog({ onAdded }: AddProviderDialogProps) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState('openai');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('');
  const [monthlyBudget, setMonthlyBudget] = useState('10');
  const [dailyBudget, setDailyBudget] = useState('1');
  const [autoLearn, setAutoLearn] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      await api.post('/api/external/config', {
        provider,
        api_key: apiKey,
        model_name: modelName || null,
        monthly_budget_usd: parseFloat(monthlyBudget) || 0,
        daily_budget_usd: parseFloat(dailyBudget) || 0,
        auto_learn: autoLearn,
      });
      onAdded();
      handleOpenChange(false);
    } catch (err) {
      if (err instanceof api.ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to add provider');
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setProvider('openai');
      setApiKey('');
      setModelName('');
      setMonthlyBudget('10');
      setDailyBudget('1');
      setAutoLearn(false);
      setError('');
    }
  }

  const selectedProvider = PROVIDERS.find((p) => p.value === provider);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>Add Provider</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add External LLM Provider</DialogTitle>
            <DialogDescription>
              Connect an external AI provider for enhanced capabilities.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-4">
            <div className="space-y-2">
              <Label>Provider</Label>
              <div className="flex flex-wrap gap-2">
                {PROVIDERS.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setProvider(p.value)}
                    className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                      provider === p.value
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-input bg-background hover:bg-accent'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="api-key">API Key</Label>
              <Input
                id="api-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={selectedProvider?.placeholder}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="model-name">Model (optional)</Label>
              <Input
                id="model-name"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder="e.g. gpt-4o, claude-sonnet-4-5-20250929"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="monthly-budget">Monthly Budget ($)</Label>
                <Input
                  id="monthly-budget"
                  type="number"
                  min="0"
                  step="0.01"
                  value={monthlyBudget}
                  onChange={(e) => setMonthlyBudget(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="daily-budget">Daily Budget ($)</Label>
                <Input
                  id="daily-budget"
                  type="number"
                  min="0"
                  step="0.01"
                  value={dailyBudget}
                  onChange={(e) => setDailyBudget(e.target.value)}
                />
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={autoLearn}
                onChange={(e) => setAutoLearn(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <span className="text-sm">
                Auto-learn: Ingest external responses into local knowledge
              </span>
            </label>

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <DialogFooter className="mt-6">
            <Button type="submit" disabled={submitting || !apiKey}>
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Adding...
                </>
              ) : (
                'Add Provider'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
