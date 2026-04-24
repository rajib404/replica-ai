'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000')
  .replace(/^http/, 'ws');

export interface ChatSource {
  entry_id: string;
  content_type: string;
  score: number;
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface ChallengeData {
  challenge_id: string;
  challenge_type: 'soft' | 'hard';
  question?: string;
  methods?: string[];
  timeout_seconds: number;
}

export interface ChallengeResultData {
  passed: boolean;
  message: string;
}

interface UseChatSocketOptions {
  ownerId: string;
  onToken: (token: string, messageId: string) => void;
  onDone: (messageId: string, threadId: string, sources: ChatSource[], isLearning: boolean, content: string) => void;
  onLearning: () => void;
  onError: (detail: string) => void;
  onChallenge?: (challenge: ChallengeData) => void;
  onChallengeResult?: (result: ChallengeResultData) => void;
  onLockout?: (message: string) => void;
}

const MAX_RETRIES = 5;

export function useChatSocket({
  ownerId,
  onToken,
  onDone,
  onLearning,
  onError,
  onChallenge,
  onChallengeResult,
  onLockout,
}: UseChatSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const retriesRef = useRef(0);
  // Monotonic ID to guard against stale onclose/onmessage from previous WebSockets
  // (React Strict Mode runs effects twice in dev, creating a race condition)
  const connIdRef = useRef(0);

  const connect = useCallback(() => {
    const token = api.getToken();
    if (!token) {
      onError('No auth token');
      setStatus('error');
      return;
    }

    // Invalidate any previous WebSocket's handlers
    const connId = ++connIdRef.current;

    setStatus('connecting');
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${ownerId}?token=${token}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (connIdRef.current !== connId) return;
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'auth_ok':
            retriesRef.current = 0;
            setStatus('connected');
            break;
          case 'token':
            onToken(data.token, data.message_id);
            break;
          case 'done':
            onDone(data.message_id, data.thread_id, data.sources ?? [], data.is_learning ?? false, data.content ?? '');
            break;
          case 'learning':
            onLearning();
            break;
          case 'challenge':
            onChallenge?.({
              challenge_id: data.challenge_id,
              challenge_type: data.challenge_type,
              question: data.question,
              methods: data.methods,
              timeout_seconds: data.timeout_seconds,
            });
            break;
          case 'challenge_result':
            onChallengeResult?.({
              passed: data.passed,
              message: data.message,
            });
            break;
          case 'lockout':
            onLockout?.(data.message ?? 'Session locked. Please re-authenticate.');
            break;
          case 'error':
            // Suppress token-expiry errors — onclose(4001) handles refresh
            if (typeof data.detail === 'string' && data.detail.includes('expired')) break;
            onError(data.detail);
            break;
        }
      } catch {
        // Ignore parse errors for non-JSON messages
      }
    };

    ws.onclose = (event) => {
      // Ignore close events from a superseded WebSocket (React Strict Mode)
      if (connIdRef.current !== connId) return;
      wsRef.current = null;

      // Auth failure — try refreshing the token before giving up
      if (event.code === 4001) {
        setStatus('connecting');
        api.refreshIfNeeded().then((ok) => {
          if (connIdRef.current !== connId) return;
          if (ok) {
            retriesRef.current = 0;
            connect();
          } else {
            setStatus('error');
            onError('Session expired. Please log in again.');
          }
        });
        return;
      }

      setStatus('disconnected');
      // Auto-reconnect with exponential backoff unless intentional close or lockout
      if (event.code !== 1000 && event.code < 4000 && retriesRef.current < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
        retriesRef.current++;
        reconnectTimer.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      if (connIdRef.current !== connId) return;
      // onclose always fires after onerror — let it handle status
    };
  }, [ownerId, onToken, onDone, onLearning, onError, onChallenge, onChallengeResult, onLockout]);

  const disconnect = useCallback(() => {
    connIdRef.current++; // Invalidate any pending close handlers
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000);
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  const sendMessage = useCallback((text: string, threadId?: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'message',
          text,
          thread_id: threadId ?? null,
        }),
      );
    }
  }, []);

  const sendChallengeResponse = useCallback(
    (challengeId: string, answer?: string, method?: string, value?: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'challenge_response',
            challenge_id: challengeId,
            answer: answer ?? null,
            method: method ?? null,
            value: value ?? null,
          }),
        );
      }
    },
    [],
  );

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { status, sendMessage, sendChallengeResponse, disconnect, reconnect: connect };
}
