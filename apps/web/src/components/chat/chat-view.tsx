'use client';

import dynamic from 'next/dynamic';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { type ChatMessage } from '@/components/chat/message-bubble';
import { SwipeableMessage } from '@/components/chat/swipeable-message';
import { ChatInput } from '@/components/chat/chat-input';
import { ChallengeModal, LockoutScreen } from '@/components/chat/challenge-modal';
import { VoiceChatButton } from '@/components/chat/voice-chat-button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Bot, Wifi, WifiOff, Brain, AlertCircle, Mic, Clock } from 'lucide-react';
import {
  useChatSocket,
  type ConnectionStatus,
  type ChatSource,
  type ChallengeData,
  type ChallengeResultData,
} from '@/lib/use-chat-socket';
import { useVoiceSocket, type VoiceStatus } from '@/lib/use-voice-socket';
import { api } from '@/lib/api';
import { useOnlineStatus } from '@/lib/hooks/use-online-status';
import { useHaptic } from '@/lib/hooks/use-haptic';
import {
  appendMessage,
  deleteMessage,
  getMessages,
  trimThreadMessages,
} from '@/lib/pwa/db';
import { flushQueue, queueChatMessage } from '@/lib/pwa/message-queue';

// Heavy children loaded only when needed.
const VideoCallView = dynamic(
  () => import('@/components/chat/video-call-view').then((m) => m.VideoCallView),
  { ssr: false },
);
const VideoMessageRecorder = dynamic(
  () => import('@/components/chat/video-message-recorder').then((m) => m.VideoMessageRecorder),
  { ssr: false },
);
const VoiceSettingsPanel = dynamic(
  () => import('@/components/chat/voice-settings-panel').then((m) => m.VoiceSettingsPanel),
  { ssr: false },
);

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: 'system-1',
    role: 'system',
    content: 'Conversation started',
    timestamp: new Date(),
  },
  {
    id: 'welcome-1',
    role: 'assistant',
    content:
      "Hello! I'm your Replica AI. I'm here to remember, learn, and help. You can tell me about yourself, share memories, or ask me anything. What would you like to talk about?",
    timestamp: new Date(),
  },
];

interface ChatViewProps {
  ownerId?: string;
}

export function ChatView({ ownerId }: ChatViewProps) {
  const resolvedOwnerId = ownerId || (typeof window !== 'undefined' ? localStorage.getItem('owner_id') : null) || '';
  const searchParams = useSearchParams();
  const router = useRouter();
  const sharedText = searchParams?.get('shared') ?? '';
  const [sharedDraft, setSharedDraft] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);
  const [isLearning, setIsLearning] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>();
  const onlineStatus = useOnlineStatus();
  const haptic = useHaptic();
  const [queuedIds, setQueuedIds] = useState<Set<string>>(new Set());
  const lastPersistedRef = useRef<Set<string>>(new Set());
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [activeChallenge, setActiveChallenge] = useState<ChallengeData | null>(null);
  const [challengeResult, setChallengeResult] = useState<ChallengeResultData | null>(null);
  const [lockoutMessage, setLockoutMessage] = useState<string | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle');
  const [transcript, setTranscript] = useState<string>('');
  const [videoCallActive, setVideoCallActive] = useState(false);
  const [videoRecorderOpen, setVideoRecorderOpen] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, scrollToBottom]);

  // Clear learning indicator after 3s
  useEffect(() => {
    if (!isLearning) return;
    const timer = setTimeout(() => setIsLearning(false), 3000);
    return () => clearTimeout(timer);
  }, [isLearning]);

  // Hydrate from IDB on mount — instant offline restore.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cached = await getMessages(threadId);
      if (cancelled || cached.length === 0) return;
      cached.forEach((m) => lastPersistedRef.current.add(m.id));
      setMessages((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        const merged = [...prev];
        for (const c of cached) {
          if (!seen.has(c.id)) merged.push(c);
        }
        merged.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
        return merged;
      });
    })();
    return () => {
      cancelled = true;
    };
    // Re-hydrate when thread changes.
  }, [threadId]);

  // Persist any newly added (or updated streaming) messages.
  useEffect(() => {
    if (!resolvedOwnerId) return;
    let cancelled = false;
    (async () => {
      for (const m of messages) {
        if (m.role === 'system') continue;
        if (m.isStreaming) continue;
        if (lastPersistedRef.current.has(m.id)) continue;
        await appendMessage(m, resolvedOwnerId, threadId);
        if (cancelled) return;
        lastPersistedRef.current.add(m.id);
      }
      if (threadId) await trimThreadMessages(threadId, 100);
    })();
    return () => {
      cancelled = true;
    };
  }, [messages, threadId, resolvedOwnerId]);

  const handleToken = useCallback((token: string, messageId: string) => {
    setIsTyping(false);

    setMessages((prev) => {
      const existingIdx = prev.findIndex((m) => m.id === messageId);
      if (existingIdx >= 0) {
        const updated = [...prev];
        updated[existingIdx] = {
          ...updated[existingIdx],
          content: updated[existingIdx].content + token,
        };
        return updated;
      }
      return [
        ...prev,
        {
          id: messageId,
          role: 'assistant' as const,
          content: token,
          timestamp: new Date(),
          isStreaming: true,
        },
      ];
    });
    setStreamingMessageId(messageId);
  }, []);

  const handleDone = useCallback(
    (messageId: string, newThreadId: string, sources: ChatSource[], learning: boolean, content: string) => {
      setThreadId(newThreadId);
      setStreamingMessageId(null);
      setIsTyping(false);

      if (learning) {
        setIsLearning(true);
      }

      setMessages((prev) => {
        const existingIdx = prev.findIndex((m) => m.id === messageId);
        if (existingIdx >= 0) {
          const updated = [...prev];
          updated[existingIdx] = { ...updated[existingIdx], isStreaming: false, sources };
          return updated;
        }
        // No matching message — streaming tokens may not have arrived (e.g. AI error).
        // Fall back to the full content carried in the done frame.
        if (content) {
          return [
            ...prev,
            {
              id: messageId,
              role: 'assistant' as const,
              content,
              timestamp: new Date(),
              sources,
            },
          ];
        }
        return prev;
      });
    },
    [],
  );

  const handleLearning = useCallback(() => {
    setIsLearning(true);
  }, []);

  const handleError = useCallback((detail: string) => {
    setIsTyping(false);
    setStreamingMessageId(null);
    setMessages((prev) => [
      ...prev,
      {
        id: `error-${Date.now()}`,
        role: 'system',
        content: `Error: ${detail}`,
        timestamp: new Date(),
      },
    ]);
  }, []);

  const handleChallenge = useCallback((challenge: ChallengeData) => {
    setIsTyping(false);
    setChallengeResult(null);
    setActiveChallenge(challenge);
  }, []);

  const handleChallengeResult = useCallback((result: ChallengeResultData) => {
    setChallengeResult(result);
    if (result.passed) {
      // Auto-dismiss after 1.5s on success
      setTimeout(() => {
        setActiveChallenge(null);
        setChallengeResult(null);
      }, 1500);
    }
  }, []);

  const handleLockout = useCallback((message: string) => {
    setIsTyping(false);
    setActiveChallenge(null);
    setLockoutMessage(message);
  }, []);

  const { status, sendMessage, sendChallengeResponse } = useChatSocket({
    ownerId: resolvedOwnerId,
    onToken: handleToken,
    onDone: handleDone,
    onLearning: handleLearning,
    onError: handleError,
    onChallenge: handleChallenge,
    onChallengeResult: handleChallengeResult,
    onLockout: handleLockout,
  });

  // ── Voice chat ──

  const handleVoiceTranscript = useCallback((t: { text: string; isFinal: boolean }) => {
    setTranscript(t.text);
    if (t.isFinal && t.text) {
      // Add user message from voice transcript
      setMessages((prev) => [
        ...prev,
        {
          id: `voice-user-${Date.now()}`,
          role: 'user',
          content: t.text,
          timestamp: new Date(),
        },
      ]);
    }
  }, []);

  const handleVoiceResponseText = useCallback(
    (resp: {
      text: string;
      messageId: string;
      threadId: string;
      sources: ChatSource[];
      isLearning: boolean;
    }) => {
      setThreadId(resp.threadId);
      setMessages((prev) => [
        ...prev,
        {
          id: resp.messageId,
          role: 'assistant',
          content: resp.text,
          timestamp: new Date(),
          sources: resp.sources,
        },
      ]);
      if (resp.isLearning) setIsLearning(true);
    },
    [],
  );

  const handleVoiceAudioOut = useCallback(
    (_meta: { format: string; durationMs: number }, audioBlob: Blob) => {
      // Auto-play the TTS response
      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      audio.play().catch(() => {});
      audio.onended = () => URL.revokeObjectURL(url);
    },
    [],
  );

  const handleVoiceDone = useCallback((messageId: string, newThreadId: string) => {
    setThreadId(newThreadId);
    setTranscript('');
  }, []);

  const handleVoiceStatusChange = useCallback((s: VoiceStatus) => {
    setVoiceStatus(s);
  }, []);

  const handleVoiceError = useCallback((detail: string) => {
    setVoiceStatus('idle');
    handleError(detail);
  }, [handleError]);

  const { connectionStatus: voiceConnectionStatus, sendAudioChunk, startAudio, endAudio, cancelAudio } =
    useVoiceSocket({
      ownerId: resolvedOwnerId,
      enabled: voiceMode,
      onTranscript: handleVoiceTranscript,
      onResponseText: handleVoiceResponseText,
      onAudioOut: handleVoiceAudioOut,
      onDone: handleVoiceDone,
      onStatusChange: handleVoiceStatusChange,
      onError: handleVoiceError,
    });

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      mediaStreamRef.current = stream;

      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });
      mediaRecorderRef.current = recorder;

      // Signal server: start audio
      startAudio('webm');

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          e.data.arrayBuffer().then((buf) => sendAudioChunk(buf));
        }
      };

      recorder.start(250); // Send chunks every 250ms
    } catch {
      handleError('Microphone access denied');
    }
  }, [startAudio, sendAudioChunk, handleError]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    endAudio();
  }, [endAudio]);

  const cancelRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    cancelAudio();
    setVoiceStatus('idle');
    setTranscript('');
  }, [cancelAudio]);

  function handleSend(text: string) {
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    haptic.light();

    // If we know we're offline, queue instead of attempting send.
    if (onlineStatus === 'offline') {
      (async () => {
        const queued = await queueChatMessage(resolvedOwnerId, text, threadId);
        setQueuedIds((prev) => {
          const next = new Set(prev);
          next.add(userMessage.id);
          next.add(queued.id);
          return next;
        });
      })();
      return;
    }

    setIsTyping(true);

    if (status === 'connected') {
      sendMessage(text, threadId);
    } else {
      handleRestFallback(text);
    }
  }

  // Drain queued messages when we come back online or the WS reconnects.
  useEffect(() => {
    if (onlineStatus !== 'online') return;
    let cancelled = false;
    (async () => {
      const result = await flushQueue(async (m) => {
        // Prefer the WS path if available, fall back to REST.
        if (status === 'connected') {
          sendMessage(m.text, m.threadId ?? threadId);
        } else {
          await api.post('/api/chat/message', {
            message: m.text,
            thread_id: m.threadId ?? threadId ?? null,
          });
        }
      });
      if (cancelled) return;
      if (result.sent > 0) haptic.success();
      setQueuedIds(new Set());
    })();
    return () => {
      cancelled = true;
    };
  }, [onlineStatus, status, sendMessage, threadId, haptic]);

  // Pre-fill from share-target redirect (?shared=...) and clear the URL param.
  useEffect(() => {
    if (!sharedText) return;
    setSharedDraft(sharedText);
    router.replace('/dashboard/chat');
  }, [sharedText, router]);

  // Listen to background-sync trigger from the service worker.
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'flush-chat-queue') {
        flushQueue(async (m) => {
          await api.post('/api/chat/message', {
            message: m.text,
            thread_id: m.threadId ?? threadId ?? null,
          });
        });
      }
    };
    navigator.serviceWorker.addEventListener('message', handler);
    return () => navigator.serviceWorker.removeEventListener('message', handler);
  }, [threadId]);

  function handleDeleteMessage(id: string) {
    setMessages((prev) => prev.filter((m) => m.id !== id));
    deleteMessage(id);
  }

  function handleCopyMessage(id: string) {
    const m = messages.find((x) => x.id === id);
    if (!m || typeof navigator === 'undefined') return;
    navigator.clipboard?.writeText(m.content).catch(() => {});
  }

  async function handleRestFallback(text: string) {
    try {
      const resp = await api.post<{
        thread_id: string;
        message_id: string;
        response: string;
        sources: ChatSource[];
        is_learning: boolean;
      }>('/api/chat/message', {
        message: text,
        thread_id: threadId ?? null,
      });

      setThreadId(resp.thread_id);

      const aiMessage: ChatMessage = {
        id: resp.message_id,
        role: 'assistant',
        content: resp.response,
        timestamp: new Date(),
        sources: resp.sources,
      };
      setMessages((prev) => [...prev, aiMessage]);

      if (resp.is_learning) {
        setIsLearning(true);
      }
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 428) {
        // Challenge required — parse the detail
        const detail = JSON.parse(err.detail);
        handleChallenge({
          challenge_id: detail.challenge_id,
          challenge_type: detail.challenge_type,
          question: detail.question,
          methods: detail.methods,
          timeout_seconds: detail.timeout_seconds,
        });
      } else if (err instanceof api.ApiError && err.status === 403) {
        handleLockout(err.detail);
      } else {
        const detail = err instanceof api.ApiError ? err.detail : 'Failed to send message';
        handleError(detail);
      }
    } finally {
      setIsTyping(false);
    }
  }

  function handleChallengeRespond(
    challengeId: string,
    answer?: string,
    method?: string,
    value?: string,
  ) {
    if (status === 'connected') {
      sendChallengeResponse(challengeId, answer, method, value);
    } else {
      // REST fallback for challenge response
      handleRestChallengeResponse(challengeId, answer, method, value);
    }
  }

  async function handleRestChallengeResponse(
    challengeId: string,
    answer?: string,
    method?: string,
    value?: string,
  ) {
    try {
      const resp = await api.post<{
        passed: boolean;
        message: string;
        new_score: number;
      }>('/api/chat/challenge', {
        challenge_id: challengeId,
        answer: answer ?? null,
        method: method ?? null,
        value: value ?? null,
      });
      handleChallengeResult({ passed: resp.passed, message: resp.message });
    } catch {
      handleChallengeResult({ passed: false, message: 'Failed to submit challenge response.' });
    }
  }

  async function handleFileAttach(file: File) {
    const formData = new FormData();
    formData.append('file', file);

    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    const audioExts = ['wav', 'mp3', 'm4a', 'ogg', 'flac', 'webm'];
    const videoExts = ['mp4', 'mov', 'avi', 'mkv'];
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif'];

    let endpoint = '/api/knowledge/document';
    let label = 'document';
    if (audioExts.includes(ext)) {
      endpoint = '/api/knowledge/audio';
      label = 'audio file';
    } else if (videoExts.includes(ext)) {
      endpoint = '/api/knowledge/video';
      label = 'video';
    } else if (imageExts.includes(ext)) {
      endpoint = '/api/knowledge/image';
      label = 'image';
    }

    setMessages((prev) => [
      ...prev,
      {
        id: `upload-${Date.now()}`,
        role: 'system',
        content: `Uploading ${label}: ${file.name}`,
        timestamp: new Date(),
      },
    ]);

    try {
      const token = api.getToken();
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}${endpoint}`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        },
      );

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(body.detail ?? 'Upload failed');
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `upload-done-${Date.now()}`,
          role: 'system',
          content: `${file.name} uploaded successfully and is being processed`,
          timestamp: new Date(),
        },
      ]);
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Upload failed';
      setMessages((prev) => [
        ...prev,
        {
          id: `upload-error-${Date.now()}`,
          role: 'system',
          content: `Failed to upload ${file.name}: ${detail}`,
          timestamp: new Date(),
        },
      ]);
    }
  }

  const handleVideoCallMessage = useCallback(
    (msg: {
      text: string;
      messageId: string;
      threadId: string;
      sources: ChatSource[];
      isLearning: boolean;
      role: 'user' | 'assistant';
    }) => {
      if (msg.threadId) setThreadId(msg.threadId);
      setMessages((prev) => [
        ...prev,
        {
          id: msg.messageId,
          role: msg.role,
          content: msg.text,
          timestamp: new Date(),
          sources: msg.role === 'assistant' ? msg.sources : undefined,
        },
      ]);
      if (msg.isLearning) setIsLearning(true);
    },
    [],
  );

  function handleVideoRecordSend(file: File) {
    handleFileAttach(file);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Video call overlay */}
      {videoCallActive && (
        <VideoCallView
          ownerId={resolvedOwnerId}
          onEnd={() => setVideoCallActive(false)}
          onMessage={handleVideoCallMessage}
        />
      )}

      {/* Video message recorder */}
      <VideoMessageRecorder
        open={videoRecorderOpen}
        onClose={() => setVideoRecorderOpen(false)}
        onSend={handleVideoRecordSend}
      />

      {/* Challenge modal */}
      {activeChallenge && (
        <ChallengeModal
          challenge={activeChallenge}
          onRespond={handleChallengeRespond}
          result={challengeResult}
          onDismiss={() => {
            setActiveChallenge(null);
            setChallengeResult(null);
          }}
        />
      )}

      {/* Lockout screen */}
      {lockoutMessage && (
        <LockoutScreen
          message={lockoutMessage}
          onReauth={() => {
            setLockoutMessage(null);
            // Redirect to auth/login page
            window.location.href = '/dashboard/settings';
          }}
        />
      )}

      {/* Status bar */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <StatusIndicator status={status} />
          {voiceMode && (
            <Badge variant="outline" className="gap-1 text-xs">
              <Mic className="h-3 w-3" />
              Voice {voiceConnectionStatus === 'connected' ? 'ready' : voiceConnectionStatus}
            </Badge>
          )}
          {isLearning && (
            <Badge variant="secondary" className="gap-1 text-xs">
              <Brain className="h-3 w-3" />
              Learning from you
            </Badge>
          )}
        </div>
        {voiceMode && <VoiceSettingsPanel />}
      </div>

      {/* Messages area */}
      <ScrollArea ref={scrollRef} className="flex-1">
        <div className="mx-auto max-w-3xl py-4">
          {messages.map((msg) => (
            <div key={msg.id} className="relative">
              <SwipeableMessage
                message={msg}
                onDelete={() => handleDeleteMessage(msg.id)}
                onCopy={() => handleCopyMessage(msg.id)}
              />
              {queuedIds.has(msg.id) && (
                <span className="absolute right-4 top-1 inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-600 dark:text-amber-300">
                  <Clock className="h-2.5 w-2.5" />
                  queued
                </span>
              )}
            </div>
          ))}

          {/* Typing indicator */}
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

      {/* Voice mode: push-to-talk + transcript */}
      {voiceMode && (
        <div className="border-t bg-card px-4 py-6">
          <div className="mx-auto flex max-w-3xl flex-col items-center gap-3">
            {transcript && (
              <p className="text-sm text-muted-foreground italic">&ldquo;{transcript}&rdquo;</p>
            )}
            <VoiceChatButton
              voiceStatus={voiceStatus}
              onStartRecording={startRecording}
              onStopRecording={stopRecording}
              onCancelRecording={cancelRecording}
              disabled={!!lockoutMessage || voiceConnectionStatus !== 'connected'}
            />
          </div>
        </div>
      )}

      {/* Text Input */}
      <ChatInput
        onSend={handleSend}
        onFileAttach={handleFileAttach}
        onVoiceToggle={() => setVoiceMode((v) => !v)}
        onVideoCall={() => setVideoCallActive(true)}
        onVideoRecord={() => setVideoRecorderOpen(true)}
        voiceEnabled={voiceMode}
        disabled={(isTyping && !streamingMessageId) || !!lockoutMessage}
        initialText={sharedDraft}
      />
    </div>
  );
}

function StatusIndicator({ status }: { status: ConnectionStatus }) {
  switch (status) {
    case 'connected':
      return (
        <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
          <Wifi className="h-3 w-3" />
          <span>Connected</span>
        </div>
      );
    case 'connecting':
      return (
        <div className="flex items-center gap-1.5 text-xs text-yellow-600 dark:text-yellow-400">
          <Wifi className="h-3 w-3 animate-pulse" />
          <span>Connecting...</span>
        </div>
      );
    case 'error':
      return (
        <div className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
          <AlertCircle className="h-3 w-3" />
          <span>Connection error</span>
        </div>
      );
    default:
      return (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <WifiOff className="h-3 w-3" />
          <span>Disconnected</span>
        </div>
      );
  }
}
