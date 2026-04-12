// TypeScript types mirroring apps/api/app/models/admin_schemas.py

export interface AdminLoginRequest {
  username: string;
  password: string;
}

export interface AdminLoginResponse {
  access_token: string;
  expires_at: string;
  username: string;
}

export interface AdminMeResponse {
  username: string;
  expires_at: string;
}

// ---------- Overview / stats ----------

export interface SystemResourceSnapshot {
  cpu_percent: number | null;
  memory_percent: number | null;
  memory_used_mb: number | null;
  memory_total_mb: number | null;
  disk_percent: number | null;
  disk_used_gb: number | null;
  disk_total_gb: number | null;
  process_rss_mb: number | null;
  uptime_seconds: number;
}

export interface SystemOverviewResponse {
  total_owners: number;
  active_instances: number;
  total_knowledge_entries: number;
  total_messages: number;
  total_conversations: number;
  approximate_storage_bytes: number;
  resources: SystemResourceSnapshot;
  generated_at: string;
}

// ---------- Owners ----------

export interface OwnerSummary {
  id: string;
  name: string | null;
  email: string | null;
  instance_count: number;
  knowledge_count: number;
  message_count: number;
  last_active_at: string | null;
  created_at: string;
}

export interface OwnerListResponse {
  items: OwnerSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface OwnerDetailResponse extends OwnerSummary {
  updated_at: string;
}

// ---------- Health ----------

export type ServiceHealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

export interface ServiceHealthEntry {
  name: string;
  status: ServiceHealthStatus;
  response_time_ms: number | null;
  last_error: string | null;
  checked_at: string;
}

// ---------- Logs ----------

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  logger_name: string;
  message: string;
  exc_info: string | null;
}

export interface LogsResponse {
  items: LogEntry[];
  total: number;
}

// ---------- Rules / config ----------

export interface RateLimits {
  per_minute?: number | null;
  per_hour?: number | null;
  per_day?: number | null;
}

export interface SystemRuleResponse {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string | null;
  personality_baseline: Record<string, unknown> | null;
  rate_limits: RateLimits | null;
  file_size_limit_bytes: number | null;
  base_model: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemRuleCreate {
  name: string;
  description?: string | null;
  system_prompt?: string | null;
  personality_baseline?: Record<string, unknown> | null;
  rate_limits?: RateLimits | null;
  file_size_limit_bytes?: number | null;
  base_model?: string | null;
  is_default?: boolean;
}

export interface SystemRuleUpdate extends Partial<SystemRuleCreate> {}

export interface SystemConfigResponse {
  id: string;
  default_rule_id: string | null;
  default_base_model: string | null;
  global_rate_limit_per_minute: number | null;
  global_file_size_limit_bytes: number | null;
  maintenance_mode: boolean;
  updated_at: string;
}

export interface SystemConfigUpdate {
  default_rule_id?: string | null;
  default_base_model?: string | null;
  global_rate_limit_per_minute?: number | null;
  global_file_size_limit_bytes?: number | null;
  maintenance_mode?: boolean;
}

// ---------- Analytics ----------

export interface TimeSeriesPoint {
  date: string;
  value: number;
}

export interface KnowledgeTypeBucket {
  content_type: string;
  count: number;
}

export interface ExternalLLMUsagePoint {
  date: string;
  provider: string;
  cost_usd: number;
  tokens: number;
}

export interface StorageProjectionPoint {
  date: string;
  value: number;
  projected: boolean;
}

// ---------- Maintenance ----------

export type MaintenanceJobType =
  | 'backup'
  | 'restart_service'
  | 'migrate'
  | 'clear_cache'
  | 'restart_loops';

export type MaintenanceJobStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface MaintenanceJobResponse {
  id: string;
  job_type: MaintenanceJobType | string;
  target: string | null;
  status: MaintenanceJobStatus | string;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_by: string;
  started_at: string;
  completed_at: string | null;
}

export type BroadcastSeverity = 'info' | 'warning' | 'critical';

export interface BroadcastRequest {
  title: string;
  body: string;
  severity: BroadcastSeverity;
  send_push: boolean;
  expires_at?: string | null;
}

export interface BroadcastResponse {
  id: string;
  title: string;
  body: string;
  severity: BroadcastSeverity | string;
  push_sent: boolean;
  push_count: number;
  created_by: string;
  created_at: string;
  expires_at: string | null;
  active: boolean;
}
