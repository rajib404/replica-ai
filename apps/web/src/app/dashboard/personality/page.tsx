'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Sparkles,
  RefreshCw,
  Loader2,
  CheckCircle2,
  XCircle,
  MessageSquare,
  Smile,
  Pencil,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────

interface TraitItem {
  name: string;
  value: string;
  confidence: number;
  confirmed: boolean | null;
}

interface CommunicationStyle {
  formality: string;
  verbosity: string;
  emoji_usage: string;
  tone: string;
}

interface HumorPatterns {
  style: string;
  frequency: string;
  examples: string[];
}

interface PersonalityProfile {
  owner_id: string;
  traits: TraitItem[];
  communication_style: CommunicationStyle;
  humor_patterns: HumorPatterns;
  values_and_beliefs: TraitItem[];
  phrases_and_idioms: string[];
  emotional_baseline: Record<string, number>;
  messages_analyzed: number;
  last_analysis_at: string | null;
}

interface EmotionDetection {
  emotion: string;
  intensity: number;
  secondary_emotions: string[];
  context_summary: string | null;
}

interface EmotionTrendEntry {
  date: string;
  emotion: string;
  intensity: number;
  count: number;
}

interface EmotionTrendResponse {
  current_emotion: EmotionDetection | null;
  trend: EmotionTrendEntry[];
  period_days: number;
}

// ─── Helpers ────────────────────────────────────────────

const EMOTION_COLORS: Record<string, string> = {
  happy: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  sad: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  anxious: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  angry: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  neutral: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  excited: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  lonely: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300',
  stressed: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
};

const EMOTION_EMOJI: Record<string, string> = {
  happy: '\u{1F60A}',
  sad: '\u{1F622}',
  anxious: '\u{1F630}',
  angry: '\u{1F621}',
  neutral: '\u{1F610}',
  excited: '\u{1F929}',
  lonely: '\u{1F614}',
  stressed: '\u{1F613}',
};

function confidenceBadge(confidence: number) {
  if (confidence >= 0.8) return <Badge variant="default" className="text-[10px]">High</Badge>;
  if (confidence >= 0.5) return <Badge variant="secondary" className="text-[10px]">Medium</Badge>;
  return <Badge variant="outline" className="text-[10px]">Low</Badge>;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ─── Component ──────────────────────────────────────────

export default function PersonalityPage() {
  const [tab, setTab] = useState<'traits' | 'emotions'>('traits');
  const [profile, setProfile] = useState<PersonalityProfile | null>(null);
  const [emotions, setEmotions] = useState<EmotionTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [profileData, emotionData] = await Promise.all([
        api.get<PersonalityProfile>('/api/personality/profile'),
        api.get<EmotionTrendResponse>('/api/personality/emotions', {
          params: { days: '7' },
        }),
      ]);
      setProfile(profileData);
      setEmotions(emotionData);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
      else setError('Failed to load personality data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleRefresh() {
    setRefreshing(true);
    setError('');
    try {
      const data = await api.post<PersonalityProfile>('/api/personality/refresh', {
        force: true,
      });
      setProfile(data);
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    } finally {
      setRefreshing(false);
    }
  }

  async function handleTraitUpdate(traitName: string, confirmed: boolean) {
    setError('');
    try {
      await api.put('/api/personality/traits', {
        updates: [{ trait_name: traitName, confirmed }],
      });
      fetchData();
    } catch (err) {
      if (err instanceof api.ApiError) setError(err.detail);
    }
  }

  if (loading && !profile) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Sparkles className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Personality</h1>
            <p className="text-sm text-muted-foreground">
              Learned traits, communication style, and emotional patterns.
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', refreshing && 'animate-spin')} />
          {refreshing ? 'Analyzing...' : 'Re-Analyze'}
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Stats bar */}
      {profile && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-xs text-muted-foreground">Messages Analyzed</p>
              <p className="text-2xl font-bold">{profile.messages_analyzed}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-xs text-muted-foreground">Traits Learned</p>
              <p className="text-2xl font-bold">
                {profile.traits.length + profile.values_and_beliefs.length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-xs text-muted-foreground">Last Analysis</p>
              <p className="text-sm font-medium">
                {profile.last_analysis_at
                  ? formatDate(profile.last_analysis_at)
                  : 'Never'}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tab switcher */}
      <div className="flex gap-2">
        {(
          [
            { key: 'traits', label: 'Traits & Style', icon: Sparkles },
            { key: 'emotions', label: 'Emotional Trends', icon: Smile },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <Button
            key={key}
            variant={tab === key ? 'default' : 'outline'}
            size="sm"
            onClick={() => setTab(key)}
          >
            <Icon className="mr-1.5 h-3.5 w-3.5" />
            {label}
          </Button>
        ))}
      </div>

      {/* Traits tab */}
      {tab === 'traits' && profile && (
        <div className="space-y-6">
          {/* Communication style */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquare className="h-4 w-4" />
                Communication Style
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-xs text-muted-foreground">Formality</p>
                  <p className="text-sm font-medium capitalize">
                    {profile.communication_style.formality}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Tone</p>
                  <p className="text-sm font-medium capitalize">
                    {profile.communication_style.tone}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Verbosity</p>
                  <p className="text-sm font-medium capitalize">
                    {profile.communication_style.verbosity}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Emoji Usage</p>
                  <p className="text-sm font-medium capitalize">
                    {profile.communication_style.emoji_usage}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Humor */}
          {profile.humor_patterns.style !== 'none' && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Humor Pattern</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Style</p>
                    <p className="text-sm font-medium capitalize">
                      {profile.humor_patterns.style.replace(/_/g, ' ')}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Frequency</p>
                    <p className="text-sm font-medium capitalize">
                      {profile.humor_patterns.frequency}
                    </p>
                  </div>
                </div>
                {profile.humor_patterns.examples.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Examples</p>
                    {profile.humor_patterns.examples.map((ex, i) => (
                      <p key={i} className="text-xs italic text-muted-foreground">
                        &ldquo;{ex}&rdquo;
                      </p>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Personality traits */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Personality Traits</CardTitle>
            </CardHeader>
            <CardContent>
              {profile.traits.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No traits learned yet. Keep chatting and click Re-Analyze!
                </p>
              ) : (
                <div className="space-y-3">
                  {profile.traits.map((trait) => (
                    <div
                      key={trait.name}
                      className="flex items-start justify-between rounded-md border p-3"
                    >
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{trait.name}</p>
                          {confidenceBadge(trait.confidence)}
                          {trait.confirmed === true && (
                            <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                          )}
                          {trait.confirmed === false && (
                            <XCircle className="h-3.5 w-3.5 text-red-500" />
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{trait.value}</p>
                      </div>
                      <div className="ml-3 flex gap-1">
                        <Button
                          variant={trait.confirmed === true ? 'default' : 'outline'}
                          size="sm"
                          className="h-7 px-2"
                          onClick={() => handleTraitUpdate(trait.name, true)}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant={trait.confirmed === false ? 'destructive' : 'outline'}
                          size="sm"
                          className="h-7 px-2"
                          onClick={() => handleTraitUpdate(trait.name, false)}
                        >
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Values & beliefs */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Values & Beliefs</CardTitle>
            </CardHeader>
            <CardContent>
              {profile.values_and_beliefs.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No values detected yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {profile.values_and_beliefs.map((val) => (
                    <div
                      key={val.name}
                      className="flex items-start justify-between rounded-md border p-3"
                    >
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{val.name}</p>
                          {confidenceBadge(val.confidence)}
                          {val.confirmed === true && (
                            <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                          )}
                          {val.confirmed === false && (
                            <XCircle className="h-3.5 w-3.5 text-red-500" />
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{val.value}</p>
                      </div>
                      <div className="ml-3 flex gap-1">
                        <Button
                          variant={val.confirmed === true ? 'default' : 'outline'}
                          size="sm"
                          className="h-7 px-2"
                          onClick={() => handleTraitUpdate(`value:${val.name}`, true)}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant={val.confirmed === false ? 'destructive' : 'outline'}
                          size="sm"
                          className="h-7 px-2"
                          onClick={() => handleTraitUpdate(`value:${val.name}`, false)}
                        >
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Phrases */}
          {profile.phrases_and_idioms.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Common Phrases</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {profile.phrases_and_idioms.map((phrase, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">
                      &ldquo;{phrase}&rdquo;
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Emotions tab */}
      {tab === 'emotions' && emotions && (
        <div className="space-y-6">
          {/* Current emotion */}
          {emotions.current_emotion && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">How Am I Feeling?</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4">
                  <span className="text-4xl">
                    {EMOTION_EMOJI[emotions.current_emotion.emotion] ?? '\u{1F610}'}
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Badge
                        className={cn(
                          'capitalize',
                          EMOTION_COLORS[emotions.current_emotion.emotion] ??
                            EMOTION_COLORS.neutral,
                        )}
                      >
                        {emotions.current_emotion.emotion}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Intensity: {Math.round(emotions.current_emotion.intensity * 100)}%
                      </span>
                    </div>
                    {emotions.current_emotion.context_summary && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {emotions.current_emotion.context_summary}
                      </p>
                    )}
                    {emotions.current_emotion.secondary_emotions.length > 0 && (
                      <div className="mt-2 flex gap-1">
                        {emotions.current_emotion.secondary_emotions.map((e) => (
                          <Badge key={e} variant="outline" className="text-[10px] capitalize">
                            {e}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Emotional baseline */}
          {profile && Object.keys(profile.emotional_baseline).length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Emotional Baseline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(profile.emotional_baseline)
                    .sort(([, a], [, b]) => b - a)
                    .map(([emotion, value]) => (
                      <div key={emotion} className="flex items-center gap-3">
                        <span className="w-16 text-xs capitalize text-muted-foreground">
                          {emotion}
                        </span>
                        <div className="h-2 flex-1 rounded-full bg-muted">
                          <div
                            className={cn(
                              'h-2 rounded-full',
                              emotion === 'happy' || emotion === 'excited'
                                ? 'bg-yellow-500'
                                : emotion === 'sad' || emotion === 'lonely'
                                  ? 'bg-blue-500'
                                  : emotion === 'angry'
                                    ? 'bg-red-500'
                                    : emotion === 'anxious' || emotion === 'stressed'
                                      ? 'bg-purple-500'
                                      : 'bg-gray-400',
                            )}
                            style={{ width: `${Math.round(value * 100)}%` }}
                          />
                        </div>
                        <span className="w-10 text-right text-xs text-muted-foreground">
                          {Math.round(value * 100)}%
                        </span>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Trend over past week */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Past {emotions.period_days} Days
              </CardTitle>
            </CardHeader>
            <CardContent>
              {emotions.trend.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No emotion data yet. Keep chatting!
                </p>
              ) : (
                <div className="space-y-2">
                  {emotions.trend.map((entry, i) => (
                    <div
                      key={`${entry.date}-${entry.emotion}-${i}`}
                      className="flex items-center gap-3 rounded-md border p-2"
                    >
                      <span className="w-20 text-xs text-muted-foreground">
                        {entry.date}
                      </span>
                      <Badge
                        className={cn(
                          'capitalize text-[10px]',
                          EMOTION_COLORS[entry.emotion] ?? EMOTION_COLORS.neutral,
                        )}
                      >
                        {EMOTION_EMOJI[entry.emotion] ?? ''} {entry.emotion}
                      </Badge>
                      <div className="h-1.5 flex-1 rounded-full bg-muted">
                        <div
                          className="h-1.5 rounded-full bg-primary/60"
                          style={{ width: `${Math.round(entry.intensity * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        x{entry.count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
