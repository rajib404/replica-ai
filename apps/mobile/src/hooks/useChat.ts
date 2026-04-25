import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { getToken, setToken } from "../store/auth";
import { WS_ENDPOINTS, ENDPOINTS } from "../api/endpoints";

const WS_URL = process.env.EXPO_PUBLIC_WS_URL ?? "ws://localhost:8000";
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

async function refreshAccessToken(): Promise<string | null> {
  try {
    const refreshToken = await getToken("refresh");
    if (!refreshToken) return null;
    const { data } = await axios.post(`${API_URL}${ENDPOINTS.AUTH_REFRESH}`, {
      refresh_token: refreshToken,
    });
    const newAccess: string = data.tokens.access_token;
    const newRefresh: string = data.tokens.refresh_token;
    await setToken("access", newAccess);
    await setToken("refresh", newRefresh);
    return newAccess;
  } catch {
    return null;
  }
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Array<{ title?: string; url?: string }>;
  degraded?: boolean;
}

export type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

export function useChat(ownerId: string, _accessToken: string, initialThreadId?: string) {
  const ws = useRef<WebSocket | null>(null);
  const streamBuffer = useRef(""); // accumulate tokens without re-rendering on each one
  const isRefreshing = useRef(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [activeThreadId, setActiveThreadId] = useState<string | undefined>(initialThreadId);
  const [degraded, setDegraded] = useState(false);

  // Sync external threadId into state (handles async resolution in the tab screen)
  useEffect(() => {
    if (initialThreadId) setActiveThreadId(initialThreadId);
  }, [initialThreadId]);

  const handleMessage = useCallback((raw: string) => {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }

    switch (msg.type) {
      case "auth_ok":
        break;

      // Server type: "token"
      case "token": {
        setIsThinking(false);
        streamBuffer.current += (msg.token as string) ?? "";
        setStreamingText(streamBuffer.current);
        break;
      }

      // Server type: "done"
      case "done": {
        setIsThinking(false);
        const finalText = streamBuffer.current || ((msg.content as string) ?? "");
        streamBuffer.current = "";
        setStreamingText("");

        if (finalText) {
          setMessages((prev) => [
            ...prev,
            {
              id: (msg.message_id as string) ?? `ai-${Date.now()}`,
              role: "assistant",
              text: finalText,
              sources: (msg.sources as ChatMessage["sources"]) ?? [],
              degraded: !!(msg.degraded),
            },
          ]);
        }
        if (msg.thread_id) setActiveThreadId(msg.thread_id as string);
        if (msg.degraded) setDegraded(true);
        break;
      }

      case "learning":
        break;

      case "error":
        console.warn("WS server error:", msg.detail);
        break;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!ownerId) return;
    if (ws.current?.readyState === WebSocket.OPEN) return;

    // Always read token fresh from storage so refreshed tokens are used
    const token = await getToken("access");
    if (!token) {
      setConnectionState("error");
      return;
    }

    setConnectionState("connecting");
    const url = `${WS_URL}${WS_ENDPOINTS.CHAT(ownerId, token)}`;
    const socket = new WebSocket(url);

    socket.onopen = () => setConnectionState("connected");

    socket.onclose = async (e) => {
      ws.current = null;
      // Token expired or invalid — try refreshing once then reconnect
      if ((e.code === 4001 || e.code === 4004) && !isRefreshing.current) {
        isRefreshing.current = true;
        setConnectionState("connecting");
        const newToken = await refreshAccessToken();
        isRefreshing.current = false;
        if (newToken) {
          connect();
        } else {
          setConnectionState("error");
        }
        return;
      }
      setConnectionState(e.code === 4003 ? "error" : "disconnected");
    };

    socket.onerror = () => setConnectionState("error");
    socket.onmessage = (e) => handleMessage(e.data as string);

    ws.current = socket;
  }, [ownerId, handleMessage]);

  const disconnect = useCallback(() => {
    ws.current?.close();
    ws.current = null;
    streamBuffer.current = "";
    setStreamingText("");
    setConnectionState("disconnected");
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      if (ws.current?.readyState !== WebSocket.OPEN) {
        console.warn("WS not open, state:", ws.current?.readyState);
        return;
      }

      setMessages((prev) => [
        ...prev,
        { id: `user-${Date.now()}`, role: "user", text: text.trim() },
      ]);
      setIsThinking(true);

      ws.current.send(
        JSON.stringify({
          type: "message",
          text: text.trim(),
          ...(activeThreadId ? { thread_id: activeThreadId } : {}),
        })
      );
    },
    [activeThreadId]
  );

  const loadHistory = useCallback((history: ChatMessage[]) => {
    setMessages(history);
  }, []);

  return {
    messages,
    streamingText,
    isThinking,
    connectionState,
    activeThreadId,
    degraded,
    connect,
    disconnect,
    sendMessage,
    loadHistory,
  };
}
