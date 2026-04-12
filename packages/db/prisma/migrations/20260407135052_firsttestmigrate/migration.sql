/*
  Warnings:

  - Added the required column `updated_at` to the `billing_configs` table without a default value. This is not possible if the table is not empty.
  - Added the required column `updated_at` to the `external_llm_configs` table without a default value. This is not possible if the table is not empty.

*/
-- CreateEnum
CREATE TYPE "PaymentStatus" AS ENUM ('succeeded', 'failed', 'pending', 'refunded');

-- CreateEnum
CREATE TYPE "DomainRuleType" AS ENUM ('allow', 'block');

-- CreateEnum
CREATE TYPE "MonitorStatus" AS ENUM ('active', 'paused', 'triggered');

-- AlterTable
ALTER TABLE "billing_configs" ADD COLUMN     "card_brand" TEXT,
ADD COLUMN     "card_last_four" TEXT,
ADD COLUMN     "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN     "hosting_expires_at" TIMESTAMP(3),
ADD COLUMN     "next_retry_at" TIMESTAMP(3),
ADD COLUMN     "payment_retry_count" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "stripe_customer_id" TEXT,
ADD COLUMN     "stripe_subscription_id" TEXT,
ADD COLUMN     "survival_mode" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "survival_mode_entered_at" TIMESTAMP(3),
ADD COLUMN     "updated_at" TIMESTAMP(3) NOT NULL;

-- AlterTable
ALTER TABLE "external_llm_configs" ADD COLUMN     "auto_learn" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN     "daily_budget_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
ADD COLUMN     "model_name" TEXT,
ADD COLUMN     "updated_at" TIMESTAMP(3) NOT NULL;

-- CreateTable
CREATE TABLE "external_llm_usage_logs" (
    "id" TEXT NOT NULL,
    "config_id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "provider" "LLMProvider" NOT NULL,
    "prompt_tokens" INTEGER NOT NULL DEFAULT 0,
    "completion_tokens" INTEGER NOT NULL DEFAULT 0,
    "cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "query_text" TEXT,
    "response_text" TEXT,
    "was_sanitized" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "external_llm_usage_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payment_logs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "stripe_payment_id" TEXT,
    "amount_usd" DOUBLE PRECISION NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'usd',
    "description" TEXT NOT NULL,
    "status" "PaymentStatus" NOT NULL DEFAULT 'pending',
    "error_message" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "payment_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "survival_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "grace_period_days" INTEGER NOT NULL DEFAULT 30,
    "notify_family" BOOLEAN NOT NULL DEFAULT true,
    "weekly_reminders" BOOLEAN NOT NULL DEFAULT true,
    "never_shutdown_with_family" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "survival_configs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "browse_logs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "title" TEXT,
    "content_text" TEXT,
    "summary" TEXT,
    "status_code" INTEGER,
    "error" TEXT,
    "content_length" INTEGER NOT NULL DEFAULT 0,
    "fetch_ms" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "browse_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "page_monitors" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "keywords" JSONB,
    "interval_hours" DOUBLE PRECISION NOT NULL DEFAULT 24,
    "status" "MonitorStatus" NOT NULL DEFAULT 'active',
    "last_content_hash" TEXT,
    "last_checked_at" TIMESTAMP(3),
    "last_triggered_at" TIMESTAMP(3),
    "trigger_reason" TEXT,
    "check_count" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "page_monitors_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "browse_domain_rules" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "domain" TEXT NOT NULL,
    "rule_type" "DomainRuleType" NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "browse_domain_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "browse_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "auto_summarize" BOOLEAN NOT NULL DEFAULT true,
    "max_pages_per_day" INTEGER NOT NULL DEFAULT 50,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "browse_configs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "personality_profiles" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "traits" JSONB NOT NULL DEFAULT '{}',
    "communication_style" JSONB NOT NULL DEFAULT '{}',
    "humor_patterns" JSONB NOT NULL DEFAULT '{}',
    "values_and_beliefs" JSONB NOT NULL DEFAULT '{}',
    "phrases_and_idioms" JSONB NOT NULL DEFAULT '[]',
    "emotional_baseline" JSONB NOT NULL DEFAULT '{}',
    "messages_analyzed" INTEGER NOT NULL DEFAULT 0,
    "last_analysis_at" TIMESTAMP(3),
    "owner_confirmed" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "personality_profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "emotion_logs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "message_id" TEXT,
    "emotion" TEXT NOT NULL,
    "intensity" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "secondary_emotions" JSONB,
    "context_summary" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "emotion_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "push_subscriptions" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "endpoint" TEXT NOT NULL,
    "p256dh" TEXT NOT NULL,
    "auth" TEXT NOT NULL,
    "user_agent" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_used_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "push_subscriptions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "voice_settings" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "voice_id" TEXT NOT NULL DEFAULT 'en_US-lessac-medium',
    "speed" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "auto_play" BOOLEAN NOT NULL DEFAULT true,
    "output_format" TEXT NOT NULL DEFAULT 'mp3',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "voice_settings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "system_rules" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "system_prompt" TEXT,
    "personality_baseline" JSONB,
    "rate_limits" JSONB,
    "file_size_limit_bytes" BIGINT,
    "base_model" TEXT,
    "is_default" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "system_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "system_config" (
    "id" TEXT NOT NULL DEFAULT 'singleton',
    "default_rule_id" TEXT,
    "default_base_model" TEXT,
    "global_rate_limit_per_minute" INTEGER,
    "global_file_size_limit_bytes" BIGINT,
    "maintenance_mode" BOOLEAN NOT NULL DEFAULT false,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "system_config_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "system_broadcasts" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "severity" TEXT NOT NULL,
    "push_sent" BOOLEAN NOT NULL DEFAULT false,
    "push_count" INTEGER NOT NULL DEFAULT 0,
    "created_by" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMP(3),
    "active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "system_broadcasts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "maintenance_jobs" (
    "id" TEXT NOT NULL,
    "job_type" TEXT NOT NULL,
    "target" TEXT,
    "status" TEXT NOT NULL,
    "result" JSONB,
    "error_message" TEXT,
    "started_by" TEXT NOT NULL,
    "started_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completed_at" TIMESTAMP(3),

    CONSTRAINT "maintenance_jobs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "external_llm_usage_logs_config_id_idx" ON "external_llm_usage_logs"("config_id");

-- CreateIndex
CREATE INDEX "external_llm_usage_logs_owner_id_idx" ON "external_llm_usage_logs"("owner_id");

-- CreateIndex
CREATE INDEX "external_llm_usage_logs_created_at_idx" ON "external_llm_usage_logs"("created_at");

-- CreateIndex
CREATE INDEX "payment_logs_owner_id_idx" ON "payment_logs"("owner_id");

-- CreateIndex
CREATE INDEX "payment_logs_created_at_idx" ON "payment_logs"("created_at");

-- CreateIndex
CREATE UNIQUE INDEX "survival_configs_owner_id_key" ON "survival_configs"("owner_id");

-- CreateIndex
CREATE INDEX "browse_logs_owner_id_idx" ON "browse_logs"("owner_id");

-- CreateIndex
CREATE INDEX "browse_logs_created_at_idx" ON "browse_logs"("created_at");

-- CreateIndex
CREATE INDEX "page_monitors_owner_id_idx" ON "page_monitors"("owner_id");

-- CreateIndex
CREATE INDEX "browse_domain_rules_owner_id_idx" ON "browse_domain_rules"("owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "browse_domain_rules_owner_id_domain_key" ON "browse_domain_rules"("owner_id", "domain");

-- CreateIndex
CREATE UNIQUE INDEX "browse_configs_owner_id_key" ON "browse_configs"("owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "personality_profiles_owner_id_key" ON "personality_profiles"("owner_id");

-- CreateIndex
CREATE INDEX "emotion_logs_owner_id_idx" ON "emotion_logs"("owner_id");

-- CreateIndex
CREATE INDEX "emotion_logs_created_at_idx" ON "emotion_logs"("created_at");

-- CreateIndex
CREATE UNIQUE INDEX "push_subscriptions_endpoint_key" ON "push_subscriptions"("endpoint");

-- CreateIndex
CREATE INDEX "push_subscriptions_owner_id_idx" ON "push_subscriptions"("owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "voice_settings_owner_id_key" ON "voice_settings"("owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "system_rules_name_key" ON "system_rules"("name");

-- CreateIndex
CREATE INDEX "system_broadcasts_active_created_at_idx" ON "system_broadcasts"("active", "created_at");

-- CreateIndex
CREATE INDEX "maintenance_jobs_status_started_at_idx" ON "maintenance_jobs"("status", "started_at");

-- AddForeignKey
ALTER TABLE "external_llm_usage_logs" ADD CONSTRAINT "external_llm_usage_logs_config_id_fkey" FOREIGN KEY ("config_id") REFERENCES "external_llm_configs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payment_logs" ADD CONSTRAINT "payment_logs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "survival_configs" ADD CONSTRAINT "survival_configs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "browse_logs" ADD CONSTRAINT "browse_logs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "page_monitors" ADD CONSTRAINT "page_monitors_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "browse_domain_rules" ADD CONSTRAINT "browse_domain_rules_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "browse_configs" ADD CONSTRAINT "browse_configs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "personality_profiles" ADD CONSTRAINT "personality_profiles_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "emotion_logs" ADD CONSTRAINT "emotion_logs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "push_subscriptions" ADD CONSTRAINT "push_subscriptions_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "voice_settings" ADD CONSTRAINT "voice_settings_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;
