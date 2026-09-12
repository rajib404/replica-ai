'use client';

import { useState, type ComponentType } from 'react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Bot, User, Heart, Bookmark, BookmarkCheck, Mic, Video, FileText, ImageIcon, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { api } from '@/lib/api';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  language?: string;
  timestamp: Date;
  isStreaming?: boolean;
  sources?: { entry_id: string; content_type: string; score: number }[];
}

interface MessageBubbleProps {
  message: ChatMessage;
  onReaction?: (messageId: string, reaction: string) => void;
  onBookmark?: (messageId: string) => void;
  /** Explicit bearer token for fetching attachments. Defaults to the
   * owner's stored access_token — pass the family session token explicitly
   * when rendering inside the family chat, since that page never touches
   * the shared access_token key. */
  authToken?: string | null;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const ATTACHMENT_META: Record<string, { icon: ComponentType<{ className?: string }>; label: string }> = {
  audio: { icon: Mic, label: 'Voice recording' },
  video: { icon: Video, label: 'Video' },
  image: { icon: ImageIcon, label: 'Photo' },
  document: { icon: FileText, label: 'Document' },
};

function AttachmentChip({
  entryId,
  contentType,
  authToken,
}: {
  entryId: string;
  contentType: string;
  authToken?: string | null;
}) {
  const meta = ATTACHMENT_META[contentType];
  const [loading, setLoading] = useState(false);
  if (!meta) return null;
  const Icon = meta.icon;

  async function handleOpen() {
    setLoading(true);
    try {
      const token = authToken !== undefined ? authToken : api.getToken();
      const resp = await fetch(`${API_BASE}/api/knowledge/entries/${entryId}/file`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) return;
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleOpen}
      disabled={loading}
      className="flex items-center gap-1.5 rounded-full border bg-background/50 px-2.5 py-1 text-xs transition-colors hover:bg-accent disabled:opacity-60"
    >
      {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Icon className="h-3 w-3" />}
      {meta.label}
    </button>
  );
}

export function MessageBubble({ message, onReaction, onBookmark, authToken }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [liked, setLiked] = useState(false);
  const [bookmarked, setBookmarked] = useState(false);

  if (isSystem) {
    return (
      <div className="mx-auto my-2 max-w-md text-center">
        <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
          {message.content}
        </span>
      </div>
    );
  }

  return (
    <div className={cn('group flex gap-3 px-4 py-2', isUser ? 'flex-row-reverse' : 'flex-row')}>
      <Avatar className="mt-1 h-8 w-8 shrink-0">
        <AvatarFallback className={cn('text-xs', isUser ? 'bg-primary text-primary-foreground' : 'bg-muted')}>
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>

      <div className={cn('flex max-w-[75%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap',
            isUser
              ? 'rounded-br-md bg-primary text-primary-foreground'
              : 'rounded-bl-md bg-muted text-foreground',
          )}
        >
          {message.content}
          {message.isStreaming && (
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-current opacity-70" />
          )}
        </div>

        {!isUser && !message.isStreaming && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.sources
              .filter((s) => ATTACHMENT_META[s.content_type])
              .map((s) => (
                <AttachmentChip
                  key={s.entry_id}
                  entryId={s.entry_id}
                  contentType={s.content_type}
                  authToken={authToken}
                />
              ))}
          </div>
        )}

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground">{formatTime(message.timestamp)}</span>
          {message.language && message.language !== 'en' && (
            <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
              {message.language.toUpperCase()}
            </Badge>
          )}
          {/* Reactions — visible on hover */}
          {!isUser && !message.isStreaming && (
            <div className="flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() => {
                      setLiked(!liked);
                      onReaction?.(message.id, 'like');
                    }}
                  >
                    <Heart className={cn('h-3 w-3', liked && 'fill-red-500 text-red-500')} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Like</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() => {
                      setBookmarked(!bookmarked);
                      onBookmark?.(message.id);
                    }}
                  >
                    {bookmarked ? (
                      <BookmarkCheck className="h-3 w-3 text-primary" />
                    ) : (
                      <Bookmark className="h-3 w-3" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Bookmark</TooltipContent>
              </Tooltip>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
