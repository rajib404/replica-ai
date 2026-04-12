from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Replica AI API"
    debug: bool = False
    host_url: str = "http://localhost:8000"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/replica_ai"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI Service
    ai_service_url: str = "http://localhost:8100"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Auth / JWT
    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION"  # legacy HS256 fallback
    jwt_algorithm: str = "HS256"
    jwt_private_key_path: str = "./keys/jwt_private.pem"
    jwt_public_key_path: str = "./keys/jwt_public.pem"
    access_token_expire_minutes: int = 60  # 1 hour
    refresh_token_expire_days: int = 30  # 30 days
    connect_token_expire_minutes: int = 60
    bcrypt_cost: int = 12

    # Voice verification
    voice_similarity_threshold: float = 0.75
    voice_min_samples: int = 3
    voice_max_samples: int = 5
    voice_min_duration_sec: float = 10.0

    # Face verification
    face_similarity_threshold: float = 0.6
    face_min_samples: int = 5
    face_max_samples: int = 10
    face_max_image_size_mb: int = 10

    # Voice chat (STT / TTS)
    piper_host: str = "localhost"
    piper_port: int = 10200
    stt_model_size: str = "base"  # faster-whisper model: tiny, base, small, medium
    stt_compute_type: str = "int8"  # int8 for CPU
    stt_sample_rate: int = 16000
    tts_sample_rate: int = 22050
    tts_default_voice: str = "en_US-lessac-medium"
    voice_output_format: str = "mp3"  # mp3 or wav
    voice_vad_threshold: float = 0.5
    voice_max_audio_mb: int = 25

    # Instance management
    instance_heartbeat_timeout_seconds: int = 300

    # Sync
    sync_interval_seconds: int = 900  # 15 minutes

    # Family access
    family_invite_expire_hours: int = 48

    # Encryption
    encryption_key: str = "CHANGE-ME-32-BYTE-KEY-FOR-PROD!!"  # legacy Fernet base

    # Security: encryption at rest (AES-256-GCM derived from master key)
    encryption_master_key: str = ""  # ENV ONLY — never persisted; loss = unrecoverable data
    encryption_pbkdf2_iterations: int = 600_000
    encryption_pbkdf2_salt_bytes: int = 16
    encryption_aes_nonce_bytes: int = 12

    # Security: audit logging
    audit_log_retention_days: int = 0  # 0 = forever
    audit_log_enabled: bool = True

    # Security: rate limiting
    rate_limit_api_per_minute: int = 100
    rate_limit_auth_per_minute: int = 10
    rate_limit_enabled: bool = True

    # Security: CSP / headers
    security_headers_enabled: bool = True
    csp_report_uri: str = ""
    hsts_max_age_seconds: int = 63_072_000  # 2 years

    # Security: 2FA (TOTP)
    totp_issuer: str = "Replica AI"
    totp_digits: int = 6
    totp_period_seconds: int = 30
    totp_window: int = 1  # accept ±1 step for clock drift

    # Security: data export & deletion
    security_export_dir: str = "./storage/exports"
    security_export_ttl_hours: int = 48
    security_delete_confirm_phrase: str = "DELETE MY ACCOUNT"

    # External LLM
    external_llm_budget_alert_pct: float = 0.8  # 80% warning threshold
    external_llm_max_query_tokens: int = 4096

    # Stripe / Billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""  # hosting subscription price
    hosting_monthly_cost_usd: float = 9.99
    survival_grace_days: int = 30
    billing_check_interval_seconds: int = 86400  # daily

    # Web browsing
    browse_timeout_seconds: int = 30
    browse_max_page_bytes: int = 5_000_000  # 5 MB
    browse_user_agent: str = "ReplicaAI-Browser/1.0 (compatible; research-bot)"
    monitor_check_interval_seconds: int = 900  # 15 minutes

    # Multilingual
    translation_cache_ttl_seconds: int = 604800  # 7 days
    supported_languages: list[str] = [
        "en", "es", "ar", "bn", "hi", "zh", "fr",
        "de", "pt", "ja", "ko", "ru", "it", "tr",
    ]
    translation_external_api: str = ""  # "deepl" or "google" — empty = Ollama only
    deepl_api_key: str = ""
    google_translate_api_key: str = ""

    # Self-learning
    learning_stale_knowledge_days: int = 90  # knowledge older than this is flagged for review
    learning_daily_max_topics: int = 3  # max topics per daily routine
    learning_max_search_results: int = 5  # web search results to process per topic
    learning_consolidation_threshold: int = 10  # min similar entries before consolidation
    learning_check_interval_seconds: int = 86400  # daily

    # Fine-tuning
    finetune_min_pairs: int = 500  # recommended minimum training pairs
    finetune_max_pairs: int = 5000  # cap to avoid runaway memory use
    finetune_min_owner_message_chars: int = 30  # filter trivial messages
    finetune_eval_holdout_ratio: float = 0.10  # 10% held out for evaluation
    finetune_versions_to_keep: int = 3  # rolling history depth
    finetune_auto_trigger_messages: int = 500  # owner messages between auto re-trains
    finetune_default_base_model: str = "mistral:7b-instruct"
    finetune_data_dir: str = "./storage/finetune"
    finetune_check_interval_seconds: int = 1800  # background trigger sweep, 30 min

    # Rate limiting
    verify_max_attempts: int = 3
    verify_window_seconds: int = 900  # 15 minutes
    verify_lockout_seconds: int = 3600  # 1 hour

    # Upload size limits (bytes)
    upload_max_audio_mb: int = 50
    upload_max_video_mb: int = 500
    upload_max_document_mb: int = 25
    upload_max_image_mb: int = 10
    request_max_body_mb: int = 550  # global request body cap (covers largest upload + headroom)

    # Allowed file extensions
    upload_audio_extensions: list[str] = [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"]
    upload_video_extensions: list[str] = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    upload_document_extensions: list[str] = [".pdf", ".docx", ".txt", ".csv", ".md"]
    upload_image_extensions: list[str] = [".jpg", ".jpeg", ".png", ".webp"]

    # Per-category rate limits (requests/min)
    rate_limit_chat_per_minute: int = 60
    rate_limit_upload_per_minute: int = 20
    rate_limit_search_per_minute: int = 60
    rate_limit_billing_per_minute: int = 20

    # Retry / resilience
    retry_ollama_attempts: int = 3
    retry_ollama_backoff_base: float = 1.0  # seconds
    retry_ollama_backoff_max: float = 8.0
    retry_external_llm_attempts: int = 2
    retry_external_llm_backoff_base: float = 2.0
    retry_db_attempts: int = 3
    retry_db_backoff_base: float = 0.5

    # Graceful degradation toggles
    rag_optional: bool = True  # chat still works if Qdrant is down
    cache_optional: bool = True  # chat still works if Redis is down

    # Web Push notifications (VAPID)
    push_enabled: bool = False
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@replica.ai"
    push_ttl_seconds: int = 86400  # 1 day default TTL on push payloads

    # Admin dashboard
    admin_enabled: bool = False
    admin_user: str = ""
    admin_pass_hash: str = ""  # bcrypt hash; generate with hash_secret()
    admin_jwt_secret: str = ""  # MUST differ from jwt_secret_key
    admin_jwt_expire_minutes: int = 60
    admin_ip_allowlist: list[str] = []  # CIDR strings; empty = allow all
    admin_log_buffer_size: int = 2000  # in-memory ring buffer capacity
    admin_backup_dir: str = "./storage/backups"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
