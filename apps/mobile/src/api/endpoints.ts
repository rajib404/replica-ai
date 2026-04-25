export const ENDPOINTS = {
  // Auth  (actual routes — docs use different names)
  AUTH_SETUP: "/api/auth/setup",       // POST — first-time owner creation
  AUTH_VERIFY: "/api/auth/verify",     // POST — returning owner identity check
  AUTH_REFRESH: "/api/auth/refresh",   // POST — token refresh

  // Chat
  CHAT_THREADS: "/api/chat/threads",
  CHAT_THREAD_MESSAGES: (id: string) => `/api/chat/threads/${id}/messages`,

  // Knowledge
  KNOWLEDGE_INGEST_TEXT: "/api/knowledge/text",
  KNOWLEDGE_INGEST_AUDIO: "/api/knowledge/audio",
  KNOWLEDGE_INGEST_VIDEO: "/api/knowledge/video",
  KNOWLEDGE_INGEST_IMAGE: "/api/knowledge/image",
  KNOWLEDGE_INGEST_DOCUMENT: "/api/knowledge/document",
  KNOWLEDGE_ENTRIES: "/api/knowledge/entries",
  KNOWLEDGE_ENTRY_FILE: (id: string) => `/api/knowledge/entries/${id}/file`,
  KNOWLEDGE_ENTRY_DELETE: (id: string) => `/api/knowledge/entries/${id}`,

  // Personality / Learning
  PERSONALITY_PROFILE: "/api/personality/profile",
  LEARNING_STATUS: "/api/learning/status",

  // Model
  MODEL_STATUS: "/api/model/status",

  // Billing
  BILLING_STATUS: "/api/billing/status",
  BILLING_CANCEL: "/api/billing/cancel",

  // Security
  SECURITY_2FA_SETUP: "/api/security/2fa/setup",
  SECURITY_2FA_VERIFY: "/api/security/2fa/verify",
  SECURITY_EXPORT: "/api/security/export",
  SECURITY_DELETE: "/api/security/delete-account",

  // Health
  HEALTH_DETAILED: "/api/health/detailed",
} as const;

export const WS_ENDPOINTS = {
  CHAT: (ownerId: string, token: string) => `/ws/chat/${ownerId}?token=${token}`,
  VOICE: (ownerId: string, token: string) => `/ws/voice/${ownerId}?token=${token}`,
} as const;
