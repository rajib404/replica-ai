// ─── Enums ───────────────────────────────────────────────

export type InstanceType = 'cloud' | 'local';
export type InstanceStatus = 'active' | 'dormant' | 'offline';
export type ContentType = 'text' | 'audio' | 'video' | 'image' | 'document';
export type AccessLevel = 'full' | 'read_only' | 'limited';
export type VerificationMethod = 'secret_word' | 'secret_event' | 'voice_match' | 'face_match' | 'none';
export type ParticipantType = 'owner' | 'family_member';
export type MessageRole = 'user' | 'assistant' | 'system';
export type LLMProvider = 'openai' | 'anthropic' | 'google' | 'custom';
export type SyncStatus = 'pending' | 'in_progress' | 'completed' | 'failed';
export type SyncType = 'full' | 'incremental' | 'model_weights';
export type ConflictResolution = 'keep_source' | 'keep_target' | 'keep_both' | 'pending';
export type LegacyTriggerType = 'manual' | 'inactivity' | 'trusted_person';
export type DomainRuleType = 'allow' | 'block';
export type MonitorStatus = 'active' | 'paused' | 'triggered';
export type PaymentStatus = 'succeeded' | 'failed' | 'pending' | 'refunded';

// ─── Domain Models ───────────────────────────────────────

export interface Owner {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  preferredLanguage: string;
  voiceProfileRef: string | null;
  faceProfileRef: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ModelInstance {
  id: string;
  ownerId: string;
  instanceType: InstanceType;
  hostname: string;
  lastSyncAt: string | null;
  status: InstanceStatus;
  version: string;
  capabilities: string[] | null;
  isPrimary: boolean;
  lastHeartbeatAt: string | null;
  apiUrl: string | null;
  createdAt: string;
}

export interface KnowledgeEntry {
  id: string;
  ownerId: string;
  contentType: ContentType;
  originalContentPath: string | null;
  originalLanguage: string;
  englishTranslation: string | null;
  embeddingId: string | null;
  metadata: Record<string, unknown> | null;
  createdAt: string;
}

export interface TopicRestrictions {
  allowed: string[];
  blocked: string[];
}

export interface TimeRestrictions {
  days: string[];
  startHour: number;
  endHour: number;
  timezone: string;
}

export interface AccessRule {
  id: string;
  ownerId: string;
  granteeName: string;
  granteeRelation: string | null;
  accessLevel: AccessLevel;
  verificationMethod: VerificationMethod;
  isActive: boolean;
  validFrom: string | null;
  validUntil: string | null;
  topicRestrictions: TopicRestrictions | null;
  timeRestrictions: TimeRestrictions | null;
  templateName: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface FamilyInvite {
  id: string;
  ruleId: string;
  isReusable: boolean;
  usesRemaining: number;
  expiresAt: string;
  createdAt: string;
}

export interface LegacyConfig {
  id: string;
  ownerId: string;
  triggerType: LegacyTriggerType;
  inactivityDays: number;
  trustedPersonRuleId: string | null;
  isActive: boolean;
  activatedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationThread {
  id: string;
  ownerId: string;
  participantType: ParticipantType;
  participantName: string;
  createdAt: string;
}

export interface Message {
  id: string;
  threadId: string;
  role: MessageRole;
  contentText: string | null;
  contentAudioPath: string | null;
  contentVideoPath: string | null;
  language: string;
  createdAt: string;
}

export interface ExternalLLMConfig {
  id: string;
  ownerId: string;
  provider: LLMProvider;
  modelName: string | null;
  monthlyBudgetUsd: number;
  dailyBudgetUsd: number;
  spentThisMonthUsd: number;
  isActive: boolean;
  autoLearn: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ExternalLLMUsageLog {
  id: string;
  configId: string;
  ownerId: string;
  provider: LLMProvider;
  promptTokens: number;
  completionTokens: number;
  costUsd: number;
  wasSanitized: boolean;
  createdAt: string;
}

export interface BillingConfig {
  id: string;
  ownerId: string;
  stripeCustomerId: string | null;
  stripeSubscriptionId: string | null;
  cardLastFour: string | null;
  cardBrand: string | null;
  hostingProvider: string | null;
  hostingExpiresAt: string | null;
  autoPayHosting: boolean;
  autoPayLlm: boolean;
  survivalMode: boolean;
  survivalModeEnteredAt: string | null;
  lastPaymentAt: string | null;
  paymentRetryCount: number;
  nextRetryAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PaymentLog {
  id: string;
  ownerId: string;
  stripePaymentId: string | null;
  amountUsd: number;
  currency: string;
  description: string;
  status: PaymentStatus;
  errorMessage: string | null;
  createdAt: string;
}

export interface SurvivalConfig {
  id: string;
  ownerId: string;
  gracePeriodDays: number;
  notifyFamily: boolean;
  weeklyReminders: boolean;
  neverShutdownWithFamily: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CostBreakdown {
  hostingMonthlyUsd: number;
  llmMonthlyUsd: number;
  storageMonthlyUsd: number;
  totalMonthlyUsd: number;
  projectedAnnualUsd: number;
  suggestions: string[];
}

export interface SyncLog {
  id: string;
  sourceInstanceId: string;
  targetInstanceId: string;
  syncType: SyncType;
  entriesSynced: number;
  totalEntries: number;
  bytesTransferred: number;
  totalBytes: number;
  status: SyncStatus;
  errorMessage: string | null;
  startedAt: string;
  completedAt: string | null;
}

export interface SyncConflict {
  id: string;
  syncLogId: string;
  entryId: string;
  entryType: string;
  sourceData: Record<string, unknown>;
  targetData: Record<string, unknown>;
  resolution: ConflictResolution;
  resolvedAt: string | null;
  createdAt: string;
}

export interface BrowseLog {
  id: string;
  ownerId: string;
  url: string;
  title: string | null;
  summary: string | null;
  statusCode: number | null;
  contentLength: number;
  fetchMs: number;
  error: string | null;
  createdAt: string;
}

export interface PageMonitor {
  id: string;
  ownerId: string;
  url: string;
  keywords: string[];
  intervalHours: number;
  status: MonitorStatus;
  lastCheckedAt: string | null;
  lastTriggeredAt: string | null;
  triggerReason: string | null;
  checkCount: number;
  createdAt: string;
}

export interface BrowseDomainRule {
  id: string;
  ownerId: string;
  domain: string;
  ruleType: DomainRuleType;
  createdAt: string;
}

export interface BrowseConfig {
  enabled: boolean;
  autoSummarize: boolean;
  maxPagesPerDay: number;
}

// ─── Language / Multilingual ─────────────────────────────

export interface LanguageDetection {
  languageCode: string;
  languageName: string;
  confidence: number;
  dialectInfo: string | null;
}

export interface TranslationResult {
  translatedText: string;
  sourceLang: string;
  targetLang: string;
  method: 'cache' | 'ollama' | 'deepl' | 'google' | 'passthrough';
}

export interface TransliterationResult {
  transliteratedText: string;
  sourceScript: string;
  targetScript: string;
}

export type SupportedLocale = 'en' | 'es' | 'ar' | 'bn' | 'hi' | 'zh' | 'fr';

// ─── Personality / Emotions ─────────────────────────────

export type EmotionType = 'happy' | 'sad' | 'anxious' | 'angry' | 'neutral' | 'excited' | 'lonely' | 'stressed';

export interface PersonalityTrait {
  name: string;
  value: string;
  confidence: number;
  confirmed: boolean | null;
}

export interface CommunicationStyle {
  formality: 'casual' | 'neutral' | 'formal';
  verbosity: 'terse' | 'moderate' | 'verbose';
  emojiUsage: 'none' | 'low' | 'moderate' | 'heavy';
  tone: 'warm' | 'friendly' | 'neutral' | 'professional' | 'blunt';
}

export interface HumorPatterns {
  style: 'dry' | 'sarcastic' | 'self_deprecating' | 'puns' | 'observational' | 'none';
  frequency: 'none' | 'low' | 'moderate' | 'high';
  examples: string[];
}

export interface PersonalityProfile {
  ownerId: string;
  traits: PersonalityTrait[];
  communicationStyle: CommunicationStyle;
  humorPatterns: HumorPatterns;
  valuesAndBeliefs: PersonalityTrait[];
  phrasesAndIdioms: string[];
  emotionalBaseline: Record<string, number>;
  messagesAnalyzed: number;
  lastAnalysisAt: string | null;
}

export interface EmotionDetection {
  emotion: EmotionType;
  intensity: number;
  secondaryEmotions: string[];
  contextSummary: string | null;
}

export interface EmotionTrendEntry {
  date: string;
  emotion: EmotionType;
  intensity: number;
  count: number;
}

export interface EmotionTrendResponse {
  currentEmotion: EmotionDetection | null;
  trend: EmotionTrendEntry[];
  periodDays: number;
}

// ─── Voice Chat ─────────────────────────────────────────

export interface VoiceInfo {
  voiceId: string;
  name: string;
  language: string;
  gender: string | null;
  description: string | null;
}

export interface VoiceSettings {
  voiceId: string;
  speed: number;
  autoPlay: boolean;
  outputFormat: 'mp3' | 'wav';
}

export interface VoiceChatTranscript {
  text: string;
  isFinal: boolean;
  confidence: number;
}

export interface VoiceChatAudioOut {
  format: string;
  sampleRate: number;
  durationMs: number;
  text: string;
}

export interface VoiceChatResponseText {
  text: string;
  messageId: string;
  threadId: string;
  sources: Array<{ entry_id: string; content_type: string; score: number }>;
  isLearning: boolean;
}

export type VoiceChatStatus = 'listening' | 'transcribing' | 'thinking' | 'speaking';

// ─── Video Call ─────────────────────────────────────────

export interface FaceVerificationResult {
  verified: boolean;
  confidence: number;
  threshold: number;
  message: string;
}

export interface FaceEnrollmentStatus {
  enrolled: boolean;
  samplesStored: number;
  samplesRequired: number;
}

export interface VideoCallStatus {
  faceVerified: boolean;
  callDurationSec: number;
}

export interface AvatarConfig {
  color?: string;
  initials?: string;
}

// ─── Self-Learning ───────────────────────────────────────

export type LearningDepth = 'shallow' | 'moderate' | 'deep';
export type LearningLogStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface KnowledgeGap {
  topic: string;
  reason: string;
  priority: 'low' | 'medium' | 'high';
}

export interface KnowledgeGapsResponse {
  gaps: KnowledgeGap[];
  entriesAnalyzed: number;
  generatedAt: string;
}

export interface LearnTopicSource {
  url: string;
  title: string | null;
  snippet: string | null;
}

export interface LearnTopicResponse {
  topic: string;
  depth: LearningDepth;
  sources: LearnTopicSource[];
  entriesCreated: number;
  summary: string;
  status: LearningLogStatus;
  errorMessage: string | null;
}

export interface LearningReportEntry {
  id: string;
  topic: string;
  depth: LearningDepth;
  sourcesUsed: LearnTopicSource[];
  entriesCreated: number;
  summary: string | null;
  status: LearningLogStatus;
  errorMessage: string | null;
  createdAt: string;
}

export interface LearningReportResponse {
  entries: LearningReportEntry[];
  total: number;
}

export interface LearningPreferences {
  enabled: boolean;
  autoTopics: string[];
  ignoreTopics: string[];
  depth: LearningDepth;
  scheduleHourUtc: number;
  maxDailyWebSearches: number;
  useExternalLlm: boolean;
}

export interface LearningPreferencesResponse extends LearningPreferences {
  ownerId: string;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface StaleKnowledgeEntry {
  entryId: string;
  topic: string;
  ageDays: number;
  lastUpdated: string;
}

export interface StaleKnowledgeResponse {
  entries: StaleKnowledgeEntry[];
  thresholdDays: number;
}

export interface ConsolidationResult {
  clustersFound: number;
  entriesMerged: number;
  newEntriesCreated: number;
  summary: string;
}

// ─── Fine-Tuning / Model Training ────────────────────────

export type FineTuneStatus =
  | 'pending'
  | 'preparing'
  | 'training'
  | 'evaluating'
  | 'completed'
  | 'failed'
  | 'rolled_back';

export interface TrainingPair {
  input: string;
  output: string;
  source: 'conversation' | 'knowledge' | 'personality';
}

export interface TrainingDataSourceStats {
  conversationPairs: number;
  knowledgePairs: number;
  personalityPairs: number;
}

export interface TrainingDataStats {
  totalPairs: number;
  sources: TrainingDataSourceStats;
  minimumRecommended: number;
  sufficient: boolean;
  samplePairs: TrainingPair[];
  generatedAt: string | null;
}

export interface GenerateDataResponse {
  stats: TrainingDataStats;
  trainingFilePath: string | null;
  warnings: string[];
}

export interface FineTuneJob {
  versionId: string;
  ownerId: string;
  version: number;
  modelName: string;
  baseModel: string;
  status: FineTuneStatus;
  trainingPairCount: number;
  trainingDataPath: string | null;
  progress: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  isActive: boolean;
  errorMessage: string | null;
  startedAt: string;
  completedAt: string | null;
}

export interface FineTuneStatusResponse {
  currentJob: FineTuneJob | null;
  queued: boolean;
  lastCompleted: FineTuneJob | null;
}

export interface ModelVersionInfo {
  versionId: string;
  version: number;
  modelName: string;
  baseModel: string;
  status: FineTuneStatus;
  isActive: boolean;
  trainingPairCount: number;
  metrics: Record<string, unknown> | null;
  startedAt: string;
  completedAt: string | null;
}

export interface ModelVersionsResponse {
  versions: ModelVersionInfo[];
  activeVersion: number | null;
  total: number;
}

export interface EvaluationSample {
  input: string;
  expected: string;
  baseResponse: string;
  fineTunedResponse: string;
  baseSimilarity: number;
  fineTunedSimilarity: number;
}

export interface EvaluationMetric {
  name: string;
  baseScore: number;
  fineTunedScore: number;
  improvement: number;
}

export interface EvaluationResult {
  version: number;
  baseModel: string;
  sampleCount: number;
  metrics: EvaluationMetric[];
  samples: EvaluationSample[];
  overallSimilarity: number;
  overallImprovement: number;
}

export interface FineTuneConfigResponse {
  ownerId: string;
  autoApprove: boolean;
  autoTriggerEnabled: boolean;
  baseModel: string;
  triggerMessageCount: number;
  lastTriggerMessageTotal: number;
  currentOwnerMessageCount: number;
  pendingMessagesUntilTrigger: number;
}

export interface RollbackResponse {
  success: boolean;
  newActiveVersion: number;
  message: string;
}

// ─── Security ────────────────────────────────────────────

export type AuditCategory =
  | 'auth'
  | 'data_access'
  | 'settings'
  | 'external_api'
  | 'payment'
  | 'security'
  | 'admin';

export type AuditOutcome = 'success' | 'failure' | 'denied';

export type DataExportStatus =
  | 'pending'
  | 'processing'
  | 'ready'
  | 'downloaded'
  | 'expired'
  | 'failed';

export interface AuditLogEntry {
  id: string;
  ownerId: string | null;
  actorId: string | null;
  actorRole: string | null;
  action: string;
  category: AuditCategory;
  resourceType: string | null;
  resourceId: string | null;
  outcome: AuditOutcome;
  ipAddress: string | null;
  userAgent: string | null;
  requestId: string | null;
  details: Record<string, unknown> | null;
  createdAt: string;
}

export interface AuditLogResponse {
  entries: AuditLogEntry[];
  total: number;
  page: number;
  pageSize: number;
}

export interface EncryptionStatusResponse {
  masterKeyConfigured: boolean;
  algorithm: string;
  kdf: string;
  kdfIterations: number;
  encryptedFieldsCount: number;
  encryptedFilesCount: number;
  warning: string;
}

export interface TwoFactorSetupResponse {
  secret: string;
  provisioningUri: string;
  qrCodeBase64: string;
  backupCodes: string[];
}

export interface TwoFactorVerifyRequest {
  code: string;
}

export interface TwoFactorVerifyResponse {
  verified: boolean;
  message: string;
}

export interface TwoFactorStatusResponse {
  enabled: boolean;
  confirmedAt: string | null;
  lastUsedAt: string | null;
  backupCodesRemaining: number;
}

export interface TwoFactorDisableRequest {
  password: string;
  code?: string | null;
}

export interface DataExportResponse {
  exportId: string;
  status: DataExportStatus;
  archiveSizeBytes: number | null;
  archiveSha256: string | null;
  downloadUrl: string | null;
  expiresAt: string | null;
  createdAt: string;
  completedAt: string | null;
}

export interface DataExportListResponse {
  exports: DataExportResponse[];
}

export interface DataDeleteRequest {
  confirmPhrase: string;
  password: string;
  totpCode?: string | null;
}

export interface DataDeleteResponse {
  deleted: boolean;
  message: string;
  deletedAt: string | null;
}

export interface SecurityHeadersStatus {
  cspEnabled: boolean;
  hstsEnabled: boolean;
  hstsMaxAge: number;
  xFrameOptions: string;
  xContentTypeOptions: string;
  rateLimitApiPerMinute: number;
  rateLimitAuthPerMinute: number;
}

// ─── API Utilities ───────────────────────────────────────

export interface ApiResponse<T> {
  data: T;
  error: string | null;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
}
