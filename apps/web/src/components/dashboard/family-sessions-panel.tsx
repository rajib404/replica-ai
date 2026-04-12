'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  MessageCircle,
  Eye,
  Send,
  RefreshCw,
  BarChart3,
  User,
  Clock,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────

interface FamilySession {
  thread_id: string;
  grantee_name: string;
  grantee_relation: string | null;
  access_level: string;
  message_count: number;
  last_message_at: string | null;
  started_at: string;
}

interface ConversationMessage {
  id: string;
  role: string;
  content_text: string | null;
  language: string;
  created_at: string;
}

interface ConversationLog {
  thread_id: string;
  grantee_name: string;
  messages: ConversationMessage[];
  has_more: boolean;
}

interface MemberAnalytics {
  grantee_name: string;
  grantee_relation: string | null;
  total_sessions: number;
  total_messages: number;
  last_visit_at: string | null;
  top_topics: string[];
}

interface AnalyticsData {
  members: MemberAnalytics[];
  total_family_messages: number;
  total_family_sessions: number;
}

// ─── Helpers ────────────────────────────────────────────

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const ACCESS_COLORS: Record<string, string> = {
  full: 'bg-green-500/15 text-green-700 border-green-500/25',
  read_only: 'bg-blue-500/15 text-blue-700 border-blue-500/25',
  limited: 'bg-orange-500/15 text-orange-700 border-orange-500/25',
};

// ─── Component ──────────────────────────────────────────

export function FamilySessionsPanel() {
  const [sessions, setSessions] = useState<FamilySession[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationLog | null>(null);
  const [interveneText, setInterveneText] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'sessions' | 'analytics'>('sessions');

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const [sessionsData, analyticsData] = await Promise.all([
        api.get<{ sessions: FamilySession[]; total: number }>('/api/access/sessions'),
        api.get<AnalyticsData>('/api/access/analytics'),
      ]);
      setSessions(sessionsData.sessions);
      setAnalytics(analyticsData);
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, [fetchSessions]);

  async function openConversation(threadId: string) {
    setSelectedThread(threadId);
    try {
      const log = await api.get<ConversationLog>(
        `/api/access/sessions/${threadId}/messages`,
      );
      setConversation(log);
    } catch {
      setConversation(null);
    }
  }

  async function handleIntervene() {
    if (!selectedThread || !interveneText.trim()) return;
    setSending(true);
    try {
      await api.post(`/api/access/sessions/${selectedThread}/intervene`, {
        message: interveneText,
      });
      setInterveneText('');
      // Reload conversation
      openConversation(selectedThread);
    } catch {
      // silently ignore
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Tab switcher */}
      <div className="flex gap-2">
        <Button
          variant={tab === 'sessions' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setTab('sessions')}
        >
          <MessageCircle className="mr-1.5 h-3.5 w-3.5" />
          Active Sessions
          {sessions.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 h-5 px-1.5 text-[10px]">
              {sessions.length}
            </Badge>
          )}
        </Button>
        <Button
          variant={tab === 'analytics' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setTab('analytics')}
        >
          <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
          Analytics
        </Button>
        <Button variant="ghost" size="sm" onClick={fetchSessions} disabled={loading}>
          <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
        </Button>
      </div>

      {tab === 'sessions' && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Session list */}
          <div className="space-y-2">
            {sessions.length === 0 ? (
              <Card>
                <CardContent className="flex h-32 flex-col items-center justify-center gap-2 text-muted-foreground">
                  <MessageCircle className="h-6 w-6" />
                  <p className="text-sm">No active family sessions.</p>
                </CardContent>
              </Card>
            ) : (
              sessions.map((s) => (
                <Card
                  key={s.thread_id}
                  className={cn(
                    'cursor-pointer transition-colors hover:bg-accent/50',
                    selectedThread === s.thread_id && 'ring-2 ring-primary',
                  )}
                  onClick={() => openConversation(s.thread_id)}
                >
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
                        <User className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-medium">{s.grantee_name}</p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          {s.grantee_relation && (
                            <span className="capitalize">{s.grantee_relation.replace('_', ' ')}</span>
                          )}
                          <span>{s.message_count} messages</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge className={cn('text-xs', ACCESS_COLORS[s.access_level] ?? '')}>
                        {s.access_level.replace('_', ' ')}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground">
                        {relativeTime(s.last_message_at)}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>

          {/* Conversation viewer */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Eye className="h-4 w-4" />
                {conversation ? `Chat with ${conversation.grantee_name}` : 'Select a session'}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {conversation ? (
                <div className="space-y-3">
                  <ScrollArea className="h-64">
                    <div className="space-y-2 pr-4">
                      {conversation.messages.map((m) => (
                        <div
                          key={m.id}
                          className={cn(
                            'rounded-lg px-3 py-2 text-sm',
                            m.role === 'user'
                              ? 'bg-primary/10 text-foreground'
                              : 'bg-muted text-foreground',
                          )}
                        >
                          <div className="mb-1 flex items-center justify-between">
                            <span className="text-[10px] font-medium uppercase text-muted-foreground">
                              {m.role === 'user' ? conversation.grantee_name : 'Replica'}
                            </span>
                            <span className="text-[10px] text-muted-foreground">
                              {new Date(m.created_at).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          </div>
                          <p className="whitespace-pre-wrap">{m.content_text}</p>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>

                  <Separator />

                  {/* Intervene */}
                  <div className="flex gap-2">
                    <Input
                      value={interveneText}
                      onChange={(e) => setInterveneText(e.target.value)}
                      placeholder="Send a message as your Replica..."
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleIntervene();
                      }}
                    />
                    <Button
                      size="icon"
                      onClick={handleIntervene}
                      disabled={!interveneText.trim() || sending}
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                  Click a session to view the conversation.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {tab === 'analytics' && analytics && (
        <div className="space-y-4">
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-3xl font-bold">{analytics.total_family_sessions}</p>
                <p className="text-xs text-muted-foreground">Total Sessions</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-3xl font-bold">{analytics.total_family_messages}</p>
                <p className="text-xs text-muted-foreground">Total Messages</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-3xl font-bold">{analytics.members.length}</p>
                <p className="text-xs text-muted-foreground">Family Members</p>
              </CardContent>
            </Card>
          </div>

          {/* Per-member analytics */}
          {analytics.members.length === 0 ? (
            <Card>
              <CardContent className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                No family member interactions yet.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-3">
              {analytics.members.map((m) => (
                <Card key={m.grantee_name}>
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
                        <User className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-medium">{m.grantee_name}</p>
                        {m.grantee_relation && (
                          <p className="text-xs text-muted-foreground capitalize">
                            {m.grantee_relation.replace('_', ' ')}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-right">
                      <div>
                        <p className="text-sm font-medium">{m.total_sessions}</p>
                        <p className="text-[10px] text-muted-foreground">sessions</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium">{m.total_messages}</p>
                        <p className="text-[10px] text-muted-foreground">messages</p>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {relativeTime(m.last_visit_at)}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
