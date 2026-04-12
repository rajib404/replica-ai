import enum
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class InstanceType(str, enum.Enum):
    cloud = "cloud"
    local = "local"


class InstanceStatus(str, enum.Enum):
    active = "active"
    dormant = "dormant"
    offline = "offline"


class SyncStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class SyncType(str, enum.Enum):
    full = "full"
    incremental = "incremental"
    model_weights = "model_weights"


class ConflictResolution(str, enum.Enum):
    keep_source = "keep_source"
    keep_target = "keep_target"
    keep_both = "keep_both"
    pending = "pending"


class AccessLevel(str, enum.Enum):
    full = "full"
    read_only = "read_only"
    limited = "limited"


class VerificationMethod(str, enum.Enum):
    secret_word = "secret_word"
    secret_event = "secret_event"
    voice_match = "voice_match"
    face_match = "face_match"
    none = "none"


class DomainRuleType(str, enum.Enum):
    allow = "allow"
    block = "block"


class MonitorStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    triggered = "triggered"


class PaymentStatus(str, enum.Enum):
    succeeded = "succeeded"
    failed = "failed"
    pending = "pending"
    refunded = "refunded"


class LLMProvider(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    custom = "custom"


class LegacyTriggerType(str, enum.Enum):
    manual = "manual"
    inactivity = "inactivity"
    trusted_person = "trusted_person"


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    voice_profile_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    face_profile_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_secret_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ModelInstance(Base):
    __tablename__ = "model_instances"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    instance_type: Mapped[InstanceType] = mapped_column(
        Enum(InstanceType, name="InstanceType", create_type=False), nullable=False
    )
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[InstanceStatus] = mapped_column(
        Enum(InstanceStatus, name="InstanceStatus", create_type=False),
        nullable=False,
        default=InstanceStatus.active,
    )
    version: Mapped[str] = mapped_column(String, nullable=False, default="0.1.0")
    capabilities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auth_token_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    api_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_instance_id: Mapped[str] = mapped_column(String, nullable=False)
    target_instance_id: Mapped[str] = mapped_column(String, nullable=False)
    sync_type: Mapped[SyncType] = mapped_column(
        Enum(SyncType, name="SyncType", create_type=False),
        nullable=False,
        default=SyncType.full,
    )
    entries_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_transferred: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="SyncStatus", create_type=False),
        nullable=False,
        default=SyncStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sync_log_id: Mapped[str] = mapped_column(String, nullable=False)
    entry_id: Mapped[str] = mapped_column(String, nullable=False)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    source_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    target_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resolution: Mapped[ConflictResolution] = mapped_column(
        Enum(ConflictResolution, name="ConflictResolution", create_type=False),
        nullable=False,
        default=ConflictResolution.pending,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class AccessRule(Base):
    __tablename__ = "access_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    grantee_name: Mapped[str] = mapped_column(String, nullable=False)
    grantee_relation: Mapped[str | None] = mapped_column(String, nullable=True)
    access_level: Mapped[AccessLevel] = mapped_column(
        Enum(AccessLevel, name="AccessLevel", create_type=False),
        nullable=False,
        default=AccessLevel.limited,
    )
    verification_method: Mapped[VerificationMethod] = mapped_column(
        Enum(VerificationMethod, name="VerificationMethod", create_type=False),
        nullable=False,
        default=VerificationMethod.none,
    )
    verification_value_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    topic_restrictions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    time_restrictions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    template_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class FamilyInvite(Base):
    __tablename__ = "family_invites"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_reusable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uses_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class LegacyConfig(Base):
    __tablename__ = "legacy_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    trigger_type: Mapped[LegacyTriggerType] = mapped_column(
        Enum(LegacyTriggerType, name="LegacyTriggerType", create_type=False),
        nullable=False,
        default=LegacyTriggerType.manual,
    )
    inactivity_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    trusted_person_rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ExternalLLMConfig(Base):
    __tablename__ = "external_llm_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[LLMProvider] = mapped_column(
        Enum(LLMProvider, name="LLMProvider", create_type=False), nullable=False
    )
    api_key_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    monthly_budget_usd: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    daily_budget_usd: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    spent_this_month_usd: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_learn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ExternalLLMUsageLog(Base):
    __tablename__ = "external_llm_usage_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    config_id: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[LLMProvider] = mapped_column(
        Enum(LLMProvider, name="LLMProvider", create_type=False), nullable=False
    )
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    query_text: Mapped[str | None] = mapped_column(String, nullable=True)
    response_text: Mapped[str | None] = mapped_column(String, nullable=True)
    was_sanitized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class BrowseLog(Base):
    __tablename__ = "browse_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetch_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class PageMonitor(Base):
    __tablename__ = "page_monitors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    interval_hours: Mapped[float] = mapped_column(Float, nullable=False, default=24.0)
    status: Mapped[MonitorStatus] = mapped_column(
        Enum(MonitorStatus, name="MonitorStatus", create_type=False),
        nullable=False,
        default=MonitorStatus.active,
    )
    last_content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trigger_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    check_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class BrowseDomainRule(Base):
    __tablename__ = "browse_domain_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    rule_type: Mapped[DomainRuleType] = mapped_column(
        Enum(DomainRuleType, name="DomainRuleType", create_type=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class BrowseConfig(Base):
    __tablename__ = "browse_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_summarize: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_pages_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class BillingConfig(Base):
    __tablename__ = "billing_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    card_token_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    card_last_four: Mapped[str | None] = mapped_column(String, nullable=True)
    card_brand: Mapped[str | None] = mapped_column(String, nullable=True)
    hosting_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    hosting_credentials_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    hosting_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_pay_hosting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_pay_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_mode_entered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    stripe_payment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="usd")
    description: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="PaymentStatus", create_type=False),
        nullable=False,
        default=PaymentStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class SurvivalConfig(Base):
    __tablename__ = "survival_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    notify_family: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weekly_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    never_shutdown_with_family: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class LearningConfig(Base):
    __tablename__ = "learning_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ignore_topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    depth: Mapped[str] = mapped_column(String, nullable=False, default="moderate")
    schedule_hour_utc: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_daily_web_searches: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    use_external_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class LearningLog(Base):
    __tablename__ = "learning_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    depth: Mapped[str] = mapped_column(String, nullable=False, default="moderate")
    sources_used: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    entries_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class FineTuneConfig(Base):
    __tablename__ = "finetune_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    auto_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_trigger_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_model: Mapped[str] = mapped_column(String, nullable=False, default="mistral:7b-instruct")
    trigger_message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    last_trigger_message_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    base_model: Mapped[str] = mapped_column(String, nullable=False)
    training_data_path: Mapped[str | None] = mapped_column(String, nullable=True)
    training_pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PersonalityProfile(Base):
    __tablename__ = "personality_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    traits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    communication_style: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    humor_patterns: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    values_and_beliefs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    phrases_and_idioms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    emotional_baseline: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    messages_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_analysis_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner_confirmed: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class EmotionLog(Base):
    __tablename__ = "emotion_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    emotion: Mapped[str] = mapped_column(String, nullable=False)
    intensity: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    secondary_emotions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    context_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class AuditLog(Base):
    """Immutable audit trail for sensitive actions. No UPDATE/DELETE allowed at app level."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)  # subject from JWT
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # categories: auth, data_access, settings, external_api, payment, security, admin
    resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=False, default="success")
    # success, failure, denied
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now(), index=True
    )


class TwoFactorAuth(Base):
    """TOTP secrets and backup codes for 2FA. Secrets stored encrypted via security service."""

    __tablename__ = "two_factor_auth"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    backup_codes_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class PushSubscription(Base):
    """Web Push subscription registered by a PWA client."""

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class DataExportRequest(Base):
    """Tracks data export requests so users can download their archive once."""

    __tablename__ = "data_export_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # pending, processing, ready, downloaded, expired, failed
    archive_path: Mapped[str | None] = mapped_column(String, nullable=True)
    archive_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    archive_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
