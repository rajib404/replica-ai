'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  GraduationCap,
  Loader2,
  Search,
  BookOpen,
  Clock,
  AlertTriangle,
  Layers,
  Settings2,
  Play,
  CheckCircle2,
  XCircle,
  ChevronDown,
  Plus,
  X,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { PushPermissionPrompt } from '@/components/pwa/push-permission-prompt';

// ─── Types ──────────────────────────────────────────────

interface KnowledgeGap {
  topic: string;
  reason: string;
  priority: string;
  suggested_queries: string[];
}

interface GapsResponse {
  gaps: KnowledgeGap[];
  total_entries: number;
  last_analysis_at: string | null;
}

interface LearnSource {
  url?: string;
  title?: string;
  type: string;
}

interface LearnResponse {
  topic: string;
  depth: string;
  sources_used: LearnSource[];
  entries_created: number;
  summary: string;
}

interface ReportEntry {
  id: string;
  topic: string;
  depth: string;
  sources_used: LearnSource[];
  entries_created: number;
  summary: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

interface ReportResponse {
  entries: ReportEntry[];
  total: number;
  page: number;
  page_size: number;
}

interface Preferences {
  enabled: boolean;
  auto_topics: string[];
  ignore_topics: string[];
  depth: string;
  schedule_hour_utc: number;
  max_daily_web_searches: number;
  use_external_llm: boolean;
}

interface PrefsResponse {
  preferences: Preferences;
  owner_id: string;
}

interface StaleEntry {
  entry_id: string;
  content_type: string;
  age_days: number;
  relevance_score: number | null;
}

interface StaleResponse {
  stale_entries: StaleEntry[];
  total_entries: number;
  threshold_days: number;
}

interface ConsolidationResult {
  groups_found: number;
  entries_consolidated: number;
  new_entries_created: number;
  summary: string;
}

// ─── Helpers ────────────────────────────────────────────

const PRIORITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  low: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
};

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ─── Component ──────────────────────────────────────────

type Tab = 'gaps' | 'history' | 'maintenance' | 'preferences';

export default function LearningPage() {
  const [tab, setTab] = useState<Tab>('gaps');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Gaps
  const [gaps, setGaps] = useState<GapsResponse | null>(null);
  const [analyzingGaps, setAnalyzingGaps] = useState(false);
  const [learningTopic, setLearningTopic] = useState('');
  const [isLearning, setIsLearning] = useState(false);
  const [learnResult, setLearnResult] = useState<LearnResponse | null>(null);

  // Quick-learn input
  const [quickTopic, setQuickTopic] = useState('');
  const [quickDepth, setQuickDepth] = useState('moderate');

  // History
  const [report, setReport] = useState<ReportResponse | null>(null);

  // Maintenance
  const [stale, setStale] = useState<StaleResponse | null>(null);
  const [consolidation, setConsolidation] = useState<ConsolidationResult | null>(null);
  const [consolidating, setConsolidating] = useState(false);

  // Preferences
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [newAutoTopic, setNewAutoTopic] = useState('');
  const [newIgnoreTopic, setNewIgnoreTopic] = useState('');

  const fetchGaps = useCallback(async () => {
    setAnalyzingGaps(true);
    setError('');
    try {
      const data = await api.get<GapsResponse>('/api/learning/gaps');
      setGaps(data);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to analyse knowledge gaps');
    } finally {
      setAnalyzingGaps(false);
      setLoading(false);
    }
  }, []);

  const fetchReport = useCallback(async () => {
    try {
      const data = await api.get<ReportResponse>('/api/learning/report');
      setReport(data);
    } catch {
      // silent
    }
  }, []);

  const fetchPrefs = useCallback(async () => {
    try {
      const data = await api.get<PrefsResponse>('/api/learning/preferences');
      setPrefs(data.preferences);
    } catch {
      // defaults
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchGaps(), fetchReport(), fetchPrefs()]);
  }, [fetchGaps, fetchReport, fetchPrefs]);

  async function handleLearnTopic(topic: string, depth: string = 'moderate') {
    setIsLearning(true);
    setLearningTopic(topic);
    setLearnResult(null);
    setError('');
    try {
      const result = await api.post<LearnResponse>('/api/learning/learn', {
        topic,
        depth,
      });
      setLearnResult(result);
      fetchReport();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Learning failed');
    } finally {
      setIsLearning(false);
      setLearningTopic('');
    }
  }

  async function handleQuickLearn() {
    if (!quickTopic.trim()) return;
    await handleLearnTopic(quickTopic.trim(), quickDepth);
    setQuickTopic('');
  }

  async function handleFetchStale() {
    try {
      const data = await api.get<StaleResponse>('/api/learning/stale');
      setStale(data);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  async function handleConsolidate() {
    setConsolidating(true);
    setError('');
    try {
      const result = await api.post<ConsolidationResult>('/api/learning/consolidate');
      setConsolidation(result);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setConsolidating(false);
    }
  }

  async function handleSavePrefs() {
    if (!prefs) return;
    setSavingPrefs(true);
    setError('');
    try {
      const data = await api.put<PrefsResponse>('/api/learning/preferences', prefs);
      setPrefs(data.preferences);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setSavingPrefs(false);
    }
  }

  if (loading && !gaps) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <GraduationCap className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Self-Learning</h1>
          <p className="text-sm text-muted-foreground">
            Autonomous knowledge acquisition and maintenance.
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <PushPermissionPrompt />

      {/* Quick learn */}
      <Card>
        <CardContent className="flex items-end gap-3 p-4">
          <div className="flex-1">
            <Label className="text-xs text-muted-foreground">Learn about a topic</Label>
            <Input
              placeholder="e.g., Mediterranean cooking, quantum computing..."
              value={quickTopic}
              onChange={(e) => setQuickTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleQuickLearn()}
              disabled={isLearning}
            />
          </div>
          <select
            className="h-9 rounded-md border bg-background px-3 text-sm"
            value={quickDepth}
            onChange={(e) => setQuickDepth(e.target.value)}
            disabled={isLearning}
          >
            <option value="shallow">Shallow</option>
            <option value="moderate">Moderate</option>
            <option value="deep">Deep</option>
          </select>
          <Button
            onClick={handleQuickLearn}
            disabled={!quickTopic.trim() || isLearning}
            size="sm"
          >
            {isLearning ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="mr-1.5 h-3.5 w-3.5" />
            )}
            Learn
          </Button>
        </CardContent>
      </Card>

      {/* Learn result */}
      {learnResult && (
        <Card className="border-green-200 dark:border-green-800">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green-600" />
              <div className="flex-1 space-y-2">
                <p className="text-sm font-medium">
                  Learned about &ldquo;{learnResult.topic}&rdquo;
                </p>
                <p className="text-xs text-muted-foreground">{learnResult.summary}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">
                    {learnResult.depth}
                  </Badge>
                  <Badge variant="secondary" className="text-[10px]">
                    {learnResult.sources_used.length} sources
                  </Badge>
                  <Badge variant="secondary" className="text-[10px]">
                    {learnResult.entries_created} entries created
                  </Badge>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setLearnResult(null)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tab switcher */}
      <div className="flex gap-2">
        {(
          [
            { key: 'gaps' as Tab, label: 'Knowledge Gaps', icon: Search },
            { key: 'history' as Tab, label: 'History', icon: Clock },
            { key: 'maintenance' as Tab, label: 'Maintenance', icon: Layers },
            { key: 'preferences' as Tab, label: 'Preferences', icon: Settings2 },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <Button
            key={key}
            variant={tab === key ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              setTab(key);
              if (key === 'maintenance' && !stale) handleFetchStale();
            }}
          >
            <Icon className="mr-1.5 h-3.5 w-3.5" />
            {label}
          </Button>
        ))}
      </div>

      {/* ─── Gaps Tab ────────────────────────────────── */}
      {tab === 'gaps' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {gaps ? `${gaps.total_entries} knowledge entries analysed` : 'Analysing...'}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchGaps}
              disabled={analyzingGaps}
            >
              {analyzingGaps ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Search className="mr-1.5 h-3.5 w-3.5" />
              )}
              Re-Analyse
            </Button>
          </div>

          {gaps && gaps.gaps.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No knowledge gaps identified. Your replica is well-informed!
            </p>
          )}

          {gaps?.gaps.map((gap, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{gap.topic}</p>
                      <Badge
                        className={cn(
                          'text-[10px]',
                          PRIORITY_COLORS[gap.priority] ?? PRIORITY_COLORS.medium,
                        )}
                      >
                        {gap.priority}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">{gap.reason}</p>
                    {gap.suggested_queries.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {gap.suggested_queries.map((q, qi) => (
                          <Badge key={qi} variant="outline" className="text-[10px]">
                            {q}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleLearnTopic(gap.topic)}
                    disabled={isLearning}
                  >
                    {isLearning && learningTopic === gap.topic ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <BookOpen className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    Learn
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ─── History Tab ─────────────────────────────── */}
      {tab === 'history' && (
        <div className="space-y-4">
          {report && report.entries.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No learning history yet. Try learning a topic above!
            </p>
          )}

          {report?.entries.map((entry) => (
            <Card key={entry.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      {entry.status === 'completed' ? (
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                      <p className="text-sm font-medium">{entry.topic}</p>
                      <Badge variant="outline" className="text-[10px]">
                        {entry.depth}
                      </Badge>
                    </div>
                    {entry.summary && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {entry.summary}
                      </p>
                    )}
                    {entry.error_message && (
                      <p className="text-xs text-destructive">{entry.error_message}</p>
                    )}
                    <div className="flex items-center gap-2 pt-1">
                      <span className="text-[10px] text-muted-foreground">
                        {formatDate(entry.created_at)}
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        {entry.sources_used.length} sources
                      </Badge>
                      <Badge variant="secondary" className="text-[10px]">
                        {entry.entries_created} entries
                      </Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {report && report.total > report.page_size && (
            <p className="text-center text-xs text-muted-foreground">
              Showing {report.entries.length} of {report.total} entries
            </p>
          )}
        </div>
      )}

      {/* ─── Maintenance Tab ─────────────────────────── */}
      {tab === 'maintenance' && (
        <div className="space-y-6">
          {/* Stale knowledge */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="h-4 w-4" />
                Stale Knowledge
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {!stale ? (
                <Button variant="outline" size="sm" onClick={handleFetchStale}>
                  <Search className="mr-1.5 h-3.5 w-3.5" />
                  Check for stale entries
                </Button>
              ) : stale.stale_entries.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No stale entries found (threshold: {stale.threshold_days} days).
                </p>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground">
                    {stale.stale_entries.length} entries older than {stale.threshold_days} days
                    (out of {stale.total_entries} total)
                  </p>
                  <div className="max-h-48 space-y-2 overflow-y-auto">
                    {stale.stale_entries.map((entry) => (
                      <div
                        key={entry.entry_id}
                        className="flex items-center justify-between rounded-md border p-2"
                      >
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[10px]">
                            {entry.content_type}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {entry.age_days} days old
                          </span>
                        </div>
                        {entry.relevance_score !== null && (
                          <span className="text-[10px] text-muted-foreground">
                            relevance: {(entry.relevance_score * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Consolidation */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Layers className="h-4 w-4" />
                Knowledge Consolidation
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Merge similar knowledge entries into comprehensive summaries.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={handleConsolidate}
                disabled={consolidating}
              >
                {consolidating ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Layers className="mr-1.5 h-3.5 w-3.5" />
                )}
                {consolidating ? 'Consolidating...' : 'Consolidate'}
              </Button>
              {consolidation && (
                <div className="rounded-md border bg-muted/50 p-3">
                  <p className="text-sm">{consolidation.summary}</p>
                  <div className="mt-2 flex gap-2">
                    <Badge variant="secondary" className="text-[10px]">
                      {consolidation.groups_found} groups
                    </Badge>
                    <Badge variant="secondary" className="text-[10px]">
                      {consolidation.entries_consolidated} merged
                    </Badge>
                    <Badge variant="secondary" className="text-[10px]">
                      {consolidation.new_entries_created} new
                    </Badge>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ─── Preferences Tab ─────────────────────────── */}
      {tab === 'preferences' && prefs && (
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Auto-Learning</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Enable toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm">Enable daily auto-learning</Label>
                  <p className="text-xs text-muted-foreground">
                    Automatically research new topics on a daily schedule.
                  </p>
                </div>
                <Switch
                  checked={prefs.enabled}
                  onCheckedChange={(v) => setPrefs({ ...prefs, enabled: v })}
                />
              </div>

              {/* Depth */}
              <div>
                <Label className="text-xs text-muted-foreground">Research Depth</Label>
                <select
                  className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
                  value={prefs.depth}
                  onChange={(e) => setPrefs({ ...prefs, depth: e.target.value })}
                >
                  <option value="shallow">Shallow (2 sources, quick scan)</option>
                  <option value="moderate">Moderate (4 sources, balanced)</option>
                  <option value="deep">Deep (8 sources, thorough)</option>
                </select>
              </div>

              {/* Schedule */}
              <div>
                <Label className="text-xs text-muted-foreground">Schedule (UTC hour)</Label>
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={prefs.schedule_hour_utc}
                  onChange={(e) =>
                    setPrefs({ ...prefs, schedule_hour_utc: parseInt(e.target.value) || 0 })
                  }
                  className="mt-1"
                />
              </div>

              {/* Max searches */}
              <div>
                <Label className="text-xs text-muted-foreground">Max daily web searches</Label>
                <Input
                  type="number"
                  min={0}
                  max={50}
                  value={prefs.max_daily_web_searches}
                  onChange={(e) =>
                    setPrefs({
                      ...prefs,
                      max_daily_web_searches: parseInt(e.target.value) || 0,
                    })
                  }
                  className="mt-1"
                />
              </div>

              {/* Use external LLM */}
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm">Use external LLM</Label>
                  <p className="text-xs text-muted-foreground">
                    Use connected external LLM for deeper synthesis (costs may apply).
                  </p>
                </div>
                <Switch
                  checked={prefs.use_external_llm}
                  onCheckedChange={(v) => setPrefs({ ...prefs, use_external_llm: v })}
                />
              </div>
            </CardContent>
          </Card>

          {/* Auto topics */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Auto-Learn Topics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Topics to automatically research during daily routines.
              </p>
              <div className="flex flex-wrap gap-2">
                {prefs.auto_topics.map((t, i) => (
                  <Badge key={i} variant="secondary" className="flex items-center gap-1">
                    {t}
                    <button
                      onClick={() =>
                        setPrefs({
                          ...prefs,
                          auto_topics: prefs.auto_topics.filter((_, idx) => idx !== i),
                        })
                      }
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="Add topic..."
                  value={newAutoTopic}
                  onChange={(e) => setNewAutoTopic(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newAutoTopic.trim()) {
                      setPrefs({
                        ...prefs,
                        auto_topics: [...prefs.auto_topics, newAutoTopic.trim()],
                      });
                      setNewAutoTopic('');
                    }
                  }}
                  className="flex-1"
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    if (newAutoTopic.trim()) {
                      setPrefs({
                        ...prefs,
                        auto_topics: [...prefs.auto_topics, newAutoTopic.trim()],
                      });
                      setNewAutoTopic('');
                    }
                  }}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Ignore topics */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Ignore Topics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Topics to skip during auto-learning.
              </p>
              <div className="flex flex-wrap gap-2">
                {prefs.ignore_topics.map((t, i) => (
                  <Badge key={i} variant="outline" className="flex items-center gap-1">
                    {t}
                    <button
                      onClick={() =>
                        setPrefs({
                          ...prefs,
                          ignore_topics: prefs.ignore_topics.filter((_, idx) => idx !== i),
                        })
                      }
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="Add topic to ignore..."
                  value={newIgnoreTopic}
                  onChange={(e) => setNewIgnoreTopic(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newIgnoreTopic.trim()) {
                      setPrefs({
                        ...prefs,
                        ignore_topics: [...prefs.ignore_topics, newIgnoreTopic.trim()],
                      });
                      setNewIgnoreTopic('');
                    }
                  }}
                  className="flex-1"
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    if (newIgnoreTopic.trim()) {
                      setPrefs({
                        ...prefs,
                        ignore_topics: [...prefs.ignore_topics, newIgnoreTopic.trim()],
                      });
                      setNewIgnoreTopic('');
                    }
                  }}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Save */}
          <Button onClick={handleSavePrefs} disabled={savingPrefs}>
            {savingPrefs ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            )}
            Save Preferences
          </Button>
        </div>
      )}
    </div>
  );
}
