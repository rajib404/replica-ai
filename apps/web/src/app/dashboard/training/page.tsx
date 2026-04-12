'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Cpu,
  Loader2,
  Play,
  Database,
  History,
  Settings2,
  RotateCcw,
  CheckCircle2,
  XCircle,
  GitBranch,
  Sparkles,
  AlertTriangle,
  TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────

interface TrainingPair {
  input: string;
  output: string;
  source: string;
}

interface SourceStats {
  conversation_pairs: number;
  knowledge_pairs: number;
  personality_pairs: number;
  filtered_out: number;
}

interface TrainingDataStats {
  owner_id: string;
  total_pairs: number;
  sources: SourceStats;
  sufficient: boolean;
  minimum_recommended: number;
  holdout_size: number;
  sample_pairs: TrainingPair[];
  generated_at: string | null;
}

interface GenerateDataResponse {
  stats: TrainingDataStats;
  training_file_path: string | null;
  warnings: string[];
}

interface FineTuneJob {
  version_id: string;
  owner_id: string;
  version: number;
  model_name: string;
  base_model: string;
  status: string;
  training_pair_count: number;
  training_data_path: string | null;
  progress: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  is_active: boolean;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

interface FineTuneStatusResponse {
  current_job: FineTuneJob | null;
  queued: boolean;
  last_completed: FineTuneJob | null;
}

interface ModelVersionInfo {
  version_id: string;
  version: number;
  model_name: string;
  base_model: string;
  status: string;
  is_active: boolean;
  training_pair_count: number;
  metrics: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
}

interface ModelVersionsResponse {
  versions: ModelVersionInfo[];
  active_version: number | null;
  total: number;
}

interface EvaluationMetric {
  name: string;
  value: number;
  description: string | null;
}

interface EvaluationSample {
  input: string;
  expected: string;
  base_response: string;
  finetuned_response: string;
  similarity_score: number | null;
}

interface EvaluationResult {
  version_id: string;
  version: number;
  sample_count: number;
  metrics: EvaluationMetric[];
  base_metrics: EvaluationMetric[];
  samples: EvaluationSample[];
  summary: string;
}

interface FineTuneConfig {
  owner_id: string;
  auto_approve: boolean;
  auto_trigger_enabled: boolean;
  base_model: string;
  trigger_message_count: number;
  last_trigger_message_total: number;
  current_owner_message_count: number;
  pending_messages_until_trigger: number;
}

// ─── Helpers ────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  preparing: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  training: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  evaluating: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  rolled_back: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ─── Component ──────────────────────────────────────────

type Tab = 'data' | 'history' | 'versions' | 'preferences';

export default function ModelTrainingPage() {
  const [tab, setTab] = useState<Tab>('data');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Data
  const [data, setData] = useState<GenerateDataResponse | null>(null);
  const [generating, setGenerating] = useState(false);

  // Status
  const [status, setStatus] = useState<FineTuneStatusResponse | null>(null);
  const [starting, setStarting] = useState(false);

  // Versions
  const [versions, setVersions] = useState<ModelVersionsResponse | null>(null);

  // Evaluation
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  // Preferences
  const [config, setConfig] = useState<FineTuneConfig | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  const fetchData = useCallback(async () => {
    setGenerating(true);
    setError('');
    try {
      const resp = await api.post<GenerateDataResponse>('/api/finetune/generate-data', {
        save_to_disk: true,
      });
      setData(resp);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to generate training data');
    } finally {
      setGenerating(false);
      setLoading(false);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await api.get<FineTuneStatusResponse>('/api/finetune/status');
      setStatus(resp);
    } catch {
      // silent
    }
  }, []);

  const fetchVersions = useCallback(async () => {
    try {
      const resp = await api.get<ModelVersionsResponse>('/api/finetune/versions');
      setVersions(resp);
    } catch {
      // silent
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const resp = await api.get<FineTuneConfig>('/api/finetune/config');
      setConfig(resp);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchData(), fetchStatus(), fetchVersions(), fetchConfig()]);
  }, [fetchData, fetchStatus, fetchVersions, fetchConfig]);

  // Poll status while a job is running
  useEffect(() => {
    if (!status?.current_job) return;
    const id = setInterval(() => {
      fetchStatus();
      fetchVersions();
    }, 4000);
    return () => clearInterval(id);
  }, [status?.current_job, fetchStatus, fetchVersions]);

  async function handleStart() {
    setStarting(true);
    setError('');
    setSuccess('');
    try {
      await api.post<FineTuneJob>('/api/finetune/start', {
        use_existing_data: true,
      });
      setSuccess('Fine-tuning started — this runs in the background.');
      setTimeout(() => {
        fetchStatus();
        fetchVersions();
      }, 1000);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to start fine-tuning');
    } finally {
      setStarting(false);
    }
  }

  async function handleEvaluate(version?: number) {
    setEvaluating(true);
    setError('');
    try {
      const resp = await api.post<EvaluationResult>('/api/finetune/evaluate', {
        version: version ?? null,
      });
      setEvaluation(resp);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Evaluation failed');
    } finally {
      setEvaluating(false);
    }
  }

  async function handleRollback(version: number) {
    setError('');
    try {
      await api.post('/api/finetune/rollback', { version });
      setSuccess(`Rolled back to version ${version}`);
      fetchVersions();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Rollback failed');
    }
  }

  async function handleSaveConfig() {
    if (!config) return;
    setSavingConfig(true);
    setError('');
    try {
      const resp = await api.put<FineTuneConfig>('/api/finetune/config', {
        auto_approve: config.auto_approve,
        auto_trigger_enabled: config.auto_trigger_enabled,
        base_model: config.base_model,
        trigger_message_count: config.trigger_message_count,
      });
      setConfig(resp);
      setSuccess('Preferences saved');
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to save preferences');
    } finally {
      setSavingConfig(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <Cpu className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Model Training</h1>
          <p className="text-sm text-muted-foreground">
            Fine-tune your replica from your own conversations and knowledge.
          </p>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="flex items-start gap-2 rounded-md border border-green-500/50 bg-green-500/10 p-3 text-sm text-green-700 dark:text-green-300">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* Status banner */}
      {status?.current_job && (
        <Card className="border-blue-500/40 bg-blue-500/5">
          <CardContent className="flex items-center gap-3 p-4">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
            <div className="flex-1">
              <p className="text-sm font-medium">
                Fine-tuning in progress (v{status.current_job.version})
              </p>
              <p className="text-xs text-muted-foreground">
                Status: {status.current_job.status} —{' '}
                {status.current_job.training_pair_count} pairs
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {(
          [
            { id: 'data', label: 'Training Data', icon: Database },
            { id: 'history', label: 'History', icon: History },
            { id: 'versions', label: 'Versions', icon: GitBranch },
            { id: 'preferences', label: 'Preferences', icon: Settings2 },
          ] as const
        ).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              'flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === id
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* TAB: Training Data */}
      {tab === 'data' && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base">Training data summary</CardTitle>
                <p className="text-xs text-muted-foreground">
                  Built from your conversations, knowledge entries, and personality.
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={fetchData}
                disabled={generating}
              >
                {generating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Database className="h-4 w-4" />
                )}
                Regenerate
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {data && (
                <>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <Stat label="Total pairs" value={data.stats.total_pairs} />
                    <Stat
                      label="Conversations"
                      value={data.stats.sources.conversation_pairs}
                    />
                    <Stat label="Knowledge" value={data.stats.sources.knowledge_pairs} />
                    <Stat
                      label="Personality"
                      value={data.stats.sources.personality_pairs}
                    />
                  </div>

                  <div className="flex items-center justify-between rounded-md bg-muted/50 p-3 text-sm">
                    <div>
                      <span className="text-muted-foreground">Recommended minimum:</span>{' '}
                      <span className="font-mono">{data.stats.minimum_recommended}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Eval holdout:</span>{' '}
                      <span className="font-mono">{data.stats.holdout_size}</span>
                    </div>
                    <div>
                      {data.stats.sufficient ? (
                        <Badge variant="default">Sufficient</Badge>
                      ) : (
                        <Badge variant="destructive">Insufficient</Badge>
                      )}
                    </div>
                  </div>

                  {data.warnings.length > 0 && (
                    <div className="space-y-1">
                      {data.warnings.map((w, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-2 rounded-md border border-yellow-500/50 bg-yellow-500/10 p-2 text-xs text-yellow-700 dark:text-yellow-300"
                        >
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {data.stats.sample_pairs.length > 0 && (
                    <div>
                      <Label className="text-xs text-muted-foreground">
                        Sample pairs
                      </Label>
                      <div className="mt-2 space-y-2">
                        {data.stats.sample_pairs.map((p, i) => (
                          <div
                            key={i}
                            className="rounded-md border bg-card p-3 text-xs"
                          >
                            <div className="mb-1 flex items-center gap-2">
                              <Badge variant="secondary" className="text-[10px]">
                                {p.source}
                              </Badge>
                            </div>
                            <p className="font-medium">{p.input}</p>
                            <p className="mt-1 text-muted-foreground">→ {p.output}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center justify-between p-4">
              <div>
                <p className="text-sm font-medium">Start fine-tuning</p>
                <p className="text-xs text-muted-foreground">
                  Creates a new model version. Runs in the background.
                </p>
              </div>
              <Button
                onClick={handleStart}
                disabled={
                  starting || !!status?.current_job || !data?.stats.total_pairs
                }
              >
                {starting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                Start Fine-Tune
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB: History */}
      {tab === 'history' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent fine-tune jobs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!status?.last_completed && !status?.current_job && (
              <p className="text-sm text-muted-foreground">No fine-tune history yet.</p>
            )}
            {status?.current_job && <JobRow job={status.current_job} />}
            {status?.last_completed && <JobRow job={status.last_completed} />}
          </CardContent>
        </Card>
      )}

      {/* TAB: Versions */}
      {tab === 'versions' && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Model versions</CardTitle>
              {versions?.active_version && (
                <Badge variant="default">Active: v{versions.active_version}</Badge>
              )}
            </CardHeader>
            <CardContent className="space-y-2">
              {!versions?.versions.length && (
                <p className="text-sm text-muted-foreground">
                  No versions yet. Run a fine-tune to create one.
                </p>
              )}
              {versions?.versions.map((v) => (
                <div
                  key={v.version_id}
                  className="flex items-center justify-between rounded-md border p-3"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-sm font-mono font-bold text-primary">
                      v{v.version}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{v.model_name}</p>
                        {v.is_active && (
                          <Badge variant="default" className="text-[10px]">
                            Active
                          </Badge>
                        )}
                        <Badge
                          className={cn('text-[10px]', STATUS_COLORS[v.status])}
                          variant="outline"
                        >
                          {v.status}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {v.training_pair_count} pairs · base: {v.base_model} ·{' '}
                        {formatDate(v.completed_at ?? v.started_at)}
                      </p>
                      {v.metrics && (
                        <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                          <TrendingUp className="h-3 w-3" />
                          similarity:{' '}
                          {(v.metrics as { style_similarity_finetuned?: number })
                            .style_similarity_finetuned ?? '—'}{' '}
                          (Δ
                          {(v.metrics as { improvement_over_base?: number })
                            .improvement_over_base ?? '—'}
                          )
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleEvaluate(v.version)}
                      disabled={evaluating || v.status !== 'completed'}
                    >
                      {evaluating ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Sparkles className="h-3.5 w-3.5" />
                      )}
                      Evaluate
                    </Button>
                    {!v.is_active && v.status === 'completed' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRollback(v.version)}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Rollback
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {evaluation && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  A/B comparison — v{evaluation.version}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm">{evaluation.summary}</p>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {evaluation.metrics.map((m) => (
                    <div key={m.name} className="rounded-md border p-3">
                      <p className="text-xs text-muted-foreground">{m.name}</p>
                      <p className="text-lg font-mono font-bold">{m.value.toFixed(4)}</p>
                      {m.description && (
                        <p className="mt-1 text-[10px] text-muted-foreground">
                          {m.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                {evaluation.samples.length > 0 && (
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Sample comparisons
                    </Label>
                    <div className="mt-2 space-y-2">
                      {evaluation.samples.map((s, i) => (
                        <div key={i} className="rounded-md border p-3 text-xs">
                          <p className="font-medium">{s.input}</p>
                          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                            <div>
                              <p className="text-[10px] uppercase text-muted-foreground">
                                Base model
                              </p>
                              <p className="text-muted-foreground">{s.base_response}</p>
                            </div>
                            <div>
                              <p className="text-[10px] uppercase text-muted-foreground">
                                Fine-tuned
                              </p>
                              <p>{s.finetuned_response}</p>
                            </div>
                          </div>
                          <p className="mt-1 text-[10px] text-muted-foreground">
                            Expected: {s.expected}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* TAB: Preferences */}
      {tab === 'preferences' && config && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Auto-improvement</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label>Enable auto-trigger</Label>
                <p className="text-xs text-muted-foreground">
                  Watch for new owner messages and queue retraining.
                </p>
              </div>
              <Switch
                checked={config.auto_trigger_enabled}
                onCheckedChange={(v) =>
                  setConfig({ ...config, auto_trigger_enabled: v })
                }
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label>Auto-approve</Label>
                <p className="text-xs text-muted-foreground">
                  Skip manual confirmation when the threshold is reached.
                </p>
              </div>
              <Switch
                checked={config.auto_approve}
                onCheckedChange={(v) => setConfig({ ...config, auto_approve: v })}
              />
            </div>

            <div>
              <Label>Base model</Label>
              <Input
                value={config.base_model}
                onChange={(e) => setConfig({ ...config, base_model: e.target.value })}
                placeholder="mistral:7b-instruct"
              />
            </div>

            <div>
              <Label>Trigger threshold (new owner messages)</Label>
              <Input
                type="number"
                min={50}
                max={10000}
                value={config.trigger_message_count}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    trigger_message_count: parseInt(e.target.value, 10) || 500,
                  })
                }
              />
            </div>

            <div className="rounded-md bg-muted/50 p-3 text-xs">
              <p>
                Owner messages so far:{' '}
                <span className="font-mono">{config.current_owner_message_count}</span>
              </p>
              <p>
                Messages until next trigger:{' '}
                <span className="font-mono">
                  {config.pending_messages_until_trigger}
                </span>
              </p>
            </div>

            <Button onClick={handleSaveConfig} disabled={savingConfig}>
              {savingConfig ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Settings2 className="h-4 w-4" />
              )}
              Save Preferences
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Sub-components ─────────────────────────────────────

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}

function JobRow({ job }: { job: FineTuneJob }) {
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm">v{job.version}</span>
          <Badge variant="outline" className={cn('text-[10px]', STATUS_COLORS[job.status])}>
            {job.status}
          </Badge>
          {job.is_active && <Badge variant="default" className="text-[10px]">Active</Badge>}
        </div>
        <p className="text-xs text-muted-foreground">
          {formatDate(job.completed_at ?? job.started_at)}
        </p>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {job.model_name} · {job.training_pair_count} pairs · base: {job.base_model}
      </p>
      {job.error_message && (
        <p className="mt-1 text-xs text-red-600">{job.error_message}</p>
      )}
    </div>
  );
}
