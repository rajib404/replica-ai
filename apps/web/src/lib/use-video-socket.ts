'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { VoiceStatus } from '@/lib/use-voice-socket';

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000')
  .replace(/^http/, 'ws');

export type VideoConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface FaceResult {
  verified: boolean;
  confidence: number;
  message: string;
}

interface VoiceResponseText {
  text: string;
  messageId: string;
  threadId: string;
  sources: Array<{ entry_id: string; content_type: string; score: number }>;
  isLearning: boolean;
}

interface VoiceAudioOut {
  format: string;
  sampleRate: number;
  durationMs: number;
  text: string;
}

interface UseVideoSocketOptions {
  ownerId: string;
  enabled: boolean;
  onTranscript: (transcript: { text: string; isFinal: boolean; confidence: number }) => void;
  onResponseText: (response: VoiceResponseText) => void;
  onAudioOut: (meta: VoiceAudioOut, audioBlob: Blob) => void;
  onDone: (messageId: string, threadId: string) => void;
  onStatusChange: (status: VoiceStatus) => void;
  onFaceResult: (result: FaceResult) => void;
  onError: (detail: string) => void;
}

export function useVideoSocket({
  ownerId,
  enabled,
  onTranscript,
  onResponseText,
  onAudioOut,
  onDone,
  onStatusChange,
  onFaceResult,
  onError,
}: UseVideoSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<VideoConnectionStatus>('disconnected');
  const connIdRef = useRef(0);
  const pendingAudioMetaRef = useRef<VoiceAudioOut | null>(null);

  const connect = useCallback(() => {
    if (!enabled) return;

    const token = api.getToken();
    if (!token) {
      onError('No auth token');
      setConnectionStatus('error');
      return;
    }

    const connId = ++connIdRef.current;
    setConnectionStatus('connecting');
    const ws = new WebSocket(`${WS_BASE}/ws/video/${ownerId}?token=${token}`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (connIdRef.current !== connId) return;

      // Binary frame = TTS audio
      if (event.data instanceof ArrayBuffer) {
        const meta = pendingAudioMetaRef.current;
        if (meta) {
          const mimeType = meta.format === 'mp3' ? 'audio/mpeg' : 'audio/wav';
          const blob = new Blob([event.data], { type: mimeType });
          onAudioOut(meta, blob);
          pendingAudioMetaRef.current = null;
        }
        return;
      }

      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'auth_ok':
            setConnectionStatus('connected');
            break;

          case 'status':
            onStatusChange(data.status as VoiceStatus);
            break;

          case 'transcript':
            onTranscript({
              text: data.text,
              isFinal: data.is_final,
              confidence: data.confidence,
            });
            break;

          case 'response_text':
            onResponseText({
              text: data.text,
              messageId: data.message_id,
              threadId: data.thread_id,
              sources: data.sources ?? [],
              isLearning: data.is_learning ?? false,
            });
            break;

          case 'audio_out':
            pendingAudioMetaRef.current = {
              format: data.format,
              sampleRate: data.sample_rate,
              durationMs: data.duration_ms,
              text: data.text,
            };
            break;

          case 'done':
            onDone(data.message_id, data.thread_id);
            onStatusChange('idle');
            break;

          case 'face_result':
            onFaceResult({
              verified: data.verified,
              confidence: data.confidence,
              message: data.message,
            });
            break;

          case 'error':
            onError(data.detail);
            onStatusChange('idle');
            break;
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      if (connIdRef.current !== connId) return;
      wsRef.current = null;
      setConnectionStatus('disconnected');
      onStatusChange('idle');
    };

    ws.onerror = () => {
      if (connIdRef.current !== connId) return;
    };
  }, [ownerId, enabled, onTranscript, onResponseText, onAudioOut, onDone, onStatusChange, onFaceResult, onError]);

  const disconnect = useCallback(() => {
    connIdRef.current++;
    if (wsRef.current) {
      wsRef.current.close(1000);
      wsRef.current = null;
    }
    setConnectionStatus('disconnected');
  }, []);

  const sendAudioChunk = useCallback((chunk: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(chunk);
    }
  }, []);

  const startAudio = useCallback((format: string = 'webm') => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: 'audio', format, is_final: false }),
      );
    }
  }, []);

  const endAudio = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: 'audio', is_final: true }),
      );
    }
  }, []);

  const cancelAudio = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }));
    }
  }, []);

  const sendFaceFrame = useCallback((jpegArrayBuffer: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Send control message first, then binary
      wsRef.current.send(JSON.stringify({ type: 'face_frame' }));
      wsRef.current.send(jpegArrayBuffer);
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }
    return () => disconnect();
  }, [enabled, connect, disconnect]);

  return {
    connectionStatus,
    sendAudioChunk,
    startAudio,
    endAudio,
    cancelAudio,
    sendFaceFrame,
    disconnect,
    reconnect: connect,
  };
}
