'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Heart,
  Bot,
  Wifi,
  WifiOff,
  AlertCircle,
  LogOut,
  Shield,
  Flower2,
  Send,
  Archive,
} from 'lucide-react';
import { MessageBubble, type ChatMessage } from '@/components/chat/message-bubble';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { type ConnectionStatus, type ChatSource } from '@/lib/use-chat-socket';
import { api } from '@/lib/api';

interface SessionInfo {
  owner_id: string;
  owner_name: string;
  grantee_name: string;
  access_level: string;
  topic_restrictions: { allowed: string[]; blocked: string[] } | null;
  time_restrictions: { days: string[]; start_hour: number; end_hour: number; timezone: string } | null;
  legacy_mode_active: boolean;
}

const ACCESS_LABELS: Record<string, string> = {
  full: 'Full Access',
  read_only: 'Read Only',
  limited: 'Limited Access',
};

export default function FamilyChatPage() {
  const router = useRouter();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>();
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [text, setText] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSignOut() {
    localStorage.removeItem('family_token');
    localStorage.removeItem('family_grantee_name');
    localStorage.removeItem('family_access_level');
    router.push('/family-access');
  }

  const [connStatus, setConnStatus] = useState<ConnectionStatus>('connecting');

  // Check we have a family token
  useEffect(() => {
    const token = localStorage.getItem('family_token');
    if (!token) {
      router.push('/family-access');
      return;
    }

    // Fetch session info
    api.get<SessionInfo>('/api/family/chat/session', { authToken: token }).then((info) => {
      setSession(info);
      setConnStatus('connected');

      // Add welcome message
      const welcomeText = info.legacy_mode_active
        ? `Welcome, ${info.grantee_name}. ${info.owner_name}'s memories and stories live on through this Replica. Feel free to ask about anything you'd like to remember together.`
        : `Hello, ${info.grantee_name}! I'm ${info.owner_name}'s Replica AI. I hold their memories and stories. What would you like to talk about?`;

      setMessages([
        {
          id: 'welcome-1',
          role: 'assistant',
          content: welcomeText,
          timestamp: new Date(),
        },
      ]);
    }).catch(() => {
      router.push('/family-access');
    });
  }, [router]);

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, scrollToBottom]);

  const handleError = useCallback((detail: string) => {
    setIsTyping(false);
    setStreamingMessageId(null);
    setMessages((prev) => [...prev, {
      id: `error-${Date.now()}`,
      role: 'system',
      content: `Error: ${detail}`,
      timestamp: new Date(),
    }]);
  }, []);

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);
    setText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    // Use REST for now (family chat endpoint)
    handleRestSend(trimmed);
  }

  async function handleRestSend(message: string) {
    try {
      const resp = await api.post<{
        thread_id: string;
        message_id: string;
        response: string;
        sources: ChatSource[];
      }>('/api/family/chat', {
        message,
        thread_id: threadId ?? null,
      }, { authToken: localStorage.getItem('family_token') });

      setThreadId(resp.thread_id);
      setConnStatus('connected');
      setMessages((prev) => [...prev, {
        id: resp.message_id,
        role: 'assistant',
        content: resp.response,
        timestamp: new Date(),
        sources: resp.sources,
      }]);
    } catch (err) {
      const detail = err instanceof api.ApiError ? err.detail : 'Failed to send message';
      setConnStatus('error');
      handleError(detail);
    } finally {
      setIsTyping(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleTextareaInput() {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  }

  if (!session) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Legacy memorial banner */}
      {session.legacy_mode_active && (
        <div className="flex items-center justify-center gap-2 border-b bg-muted/50 px-4 py-2">
          <Flower2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            In loving memory of {session.owner_name}
          </span>
          <Flower2 className="h-4 w-4 text-muted-foreground" />
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
            <Heart className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">
              Talking with {session.owner_name}&apos;s Replica
            </h1>
            <p className="text-xs text-muted-foreground">
              Hello, {session.grantee_name}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="text-xs"
          >
            <Shield className="mr-1 h-3 w-3" />
            {ACCESS_LABELS[session.access_level] ?? session.access_level}
          </Badge>
          <StatusDot status={connStatus} />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => router.push('/family/assets')}
            title="Shared photos & files"
          >
            <Archive className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handleSignOut}
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Access info bar */}
      {session.topic_restrictions && (
        <div className="border-b bg-muted/30 px-4 py-1.5">
          <p className="text-xs text-muted-foreground">
            {session.topic_restrictions.allowed.length > 0 && (
              <span>
                Topics: {session.topic_restrictions.allowed.join(', ')}
              </span>
            )}
          </p>
        </div>
      )}

      {/* Messages */}
      <ScrollArea ref={scrollRef} className="flex-1">
        <div className="mx-auto max-w-3xl py-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              authToken={typeof window !== 'undefined' ? localStorage.getItem('family_token') : null}
            />
          ))}

          {isTyping && !streamingMessageId && (
            <div className="flex items-center gap-3 px-4 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                <Bot className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="flex gap-1 rounded-2xl rounded-bl-md bg-muted px-4 py-3">
                <div className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:-0.3s]" />
                <div className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:-0.15s]" />
                <div className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/40" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Simplified input — no file upload for family members */}
      <div className="border-t bg-card p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleTextareaInput}
              placeholder="Type a message..."
              rows={1}
              disabled={isTyping && !streamingMessageId}
              className="w-full resize-none rounded-lg border bg-background px-4 py-2.5 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
          </div>
          <Button
            size="icon"
            className="h-9 w-9 shrink-0"
            onClick={handleSend}
            disabled={!text.trim() || (isTyping && !streamingMessageId)}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: ConnectionStatus }) {
  const colors: Record<ConnectionStatus, string> = {
    connected: 'bg-green-500',
    connecting: 'bg-yellow-500 animate-pulse',
    disconnected: 'bg-gray-400',
    error: 'bg-red-500',
  };
  return (
    <div className="flex items-center gap-1.5">
      <div className={`h-2 w-2 rounded-full ${colors[status]}`} />
    </div>
  );
}
