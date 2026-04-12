'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Smile, ChevronRight, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

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

export function EmotionWidget() {
  const [data, setData] = useState<EmotionTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<EmotionTrendResponse>('/api/personality/emotions', {
        params: { days: '7' },
      })
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex h-32 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const current = data.current_emotion;
  // Get unique emotions from the last 7 days
  const recentEmotions = [...new Set(data.trend.map((t) => t.emotion))];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <Smile className="h-4 w-4" />
            How Am I Feeling?
          </span>
          <Link
            href="/dashboard/personality"
            className="flex items-center text-xs text-muted-foreground hover:text-foreground"
          >
            Details
            <ChevronRight className="h-3 w-3" />
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {current ? (
          <div className="flex items-center gap-3">
            <span className="text-3xl">
              {EMOTION_EMOJI[current.emotion] ?? '\u{1F610}'}
            </span>
            <div>
              <div className="flex items-center gap-2">
                <Badge
                  className={cn(
                    'capitalize',
                    EMOTION_COLORS[current.emotion] ?? EMOTION_COLORS.neutral,
                  )}
                >
                  {current.emotion}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {Math.round(current.intensity * 100)}%
                </span>
              </div>
              {current.context_summary && (
                <p className="mt-1 text-xs text-muted-foreground line-clamp-1">
                  {current.context_summary}
                </p>
              )}
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No recent emotion data.</p>
        )}

        {recentEmotions.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <span className="text-[10px] text-muted-foreground">This week:</span>
            {recentEmotions.slice(0, 5).map((e) => (
              <Badge
                key={e}
                variant="outline"
                className="text-[10px] capitalize"
              >
                {EMOTION_EMOJI[e] ?? ''} {e}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
