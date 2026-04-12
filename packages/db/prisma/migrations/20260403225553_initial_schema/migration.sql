-- CreateEnum
CREATE TYPE "InstanceType" AS ENUM ('cloud', 'local');

-- CreateEnum
CREATE TYPE "InstanceStatus" AS ENUM ('active', 'dormant', 'offline');

-- CreateEnum
CREATE TYPE "ContentType" AS ENUM ('text', 'audio', 'video', 'image', 'document');

-- CreateEnum
CREATE TYPE "AccessLevel" AS ENUM ('full', 'read_only', 'limited');

-- CreateEnum
CREATE TYPE "VerificationMethod" AS ENUM ('secret_word', 'secret_event', 'voice_match', 'face_match', 'none');

-- CreateEnum
CREATE TYPE "ParticipantType" AS ENUM ('owner', 'family_member');

-- CreateEnum
CREATE TYPE "MessageRole" AS ENUM ('user', 'assistant', 'system');

-- CreateEnum
CREATE TYPE "LLMProvider" AS ENUM ('openai', 'anthropic', 'google', 'custom');

-- CreateEnum
CREATE TYPE "SyncStatus" AS ENUM ('pending', 'in_progress', 'completed', 'failed');

-- CreateTable
CREATE TABLE "owners" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "phone" TEXT,
    "preferred_language" TEXT NOT NULL DEFAULT 'en',
    "voice_profile_ref" TEXT,
    "face_profile_ref" TEXT,
    "auth_secret_hash" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "owners_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "model_instances" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "instance_type" "InstanceType" NOT NULL,
    "hostname" TEXT NOT NULL,
    "last_sync_at" TIMESTAMP(3),
    "status" "InstanceStatus" NOT NULL DEFAULT 'active',
    "version" TEXT NOT NULL DEFAULT '0.1.0',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "model_instances_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "knowledge_entries" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "content_type" "ContentType" NOT NULL,
    "original_content_path" TEXT,
    "original_language" TEXT NOT NULL DEFAULT 'en',
    "english_translation" TEXT,
    "embedding_id" TEXT,
    "metadata" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "knowledge_entries_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "access_rules" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "grantee_name" TEXT NOT NULL,
    "grantee_relation" TEXT,
    "access_level" "AccessLevel" NOT NULL DEFAULT 'limited',
    "verification_method" "VerificationMethod" NOT NULL DEFAULT 'none',
    "verification_value_hash" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "valid_from" TIMESTAMP(3),
    "valid_until" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "access_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversation_threads" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "participant_type" "ParticipantType" NOT NULL,
    "participant_name" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "conversation_threads_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "messages" (
    "id" TEXT NOT NULL,
    "thread_id" TEXT NOT NULL,
    "role" "MessageRole" NOT NULL,
    "content_text" TEXT,
    "content_audio_path" TEXT,
    "content_video_path" TEXT,
    "language" TEXT NOT NULL DEFAULT 'en',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "external_llm_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "provider" "LLMProvider" NOT NULL,
    "api_key_encrypted" TEXT NOT NULL,
    "monthly_budget_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "spent_this_month_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "is_active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "external_llm_configs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "billing_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "card_token_encrypted" TEXT,
    "hosting_provider" TEXT,
    "hosting_credentials_encrypted" TEXT,
    "auto_pay_hosting" BOOLEAN NOT NULL DEFAULT false,
    "auto_pay_llm" BOOLEAN NOT NULL DEFAULT false,
    "last_payment_at" TIMESTAMP(3),

    CONSTRAINT "billing_configs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sync_logs" (
    "id" TEXT NOT NULL,
    "source_instance_id" TEXT NOT NULL,
    "target_instance_id" TEXT NOT NULL,
    "entries_synced" INTEGER NOT NULL DEFAULT 0,
    "status" "SyncStatus" NOT NULL DEFAULT 'pending',
    "started_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completed_at" TIMESTAMP(3),

    CONSTRAINT "sync_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "owners_email_key" ON "owners"("email");

-- CreateIndex
CREATE INDEX "model_instances_owner_id_idx" ON "model_instances"("owner_id");

-- CreateIndex
CREATE INDEX "knowledge_entries_owner_id_idx" ON "knowledge_entries"("owner_id");

-- CreateIndex
CREATE INDEX "knowledge_entries_created_at_idx" ON "knowledge_entries"("created_at");

-- CreateIndex
CREATE INDEX "access_rules_owner_id_idx" ON "access_rules"("owner_id");

-- CreateIndex
CREATE INDEX "conversation_threads_owner_id_idx" ON "conversation_threads"("owner_id");

-- CreateIndex
CREATE INDEX "messages_thread_id_idx" ON "messages"("thread_id");

-- CreateIndex
CREATE INDEX "messages_created_at_idx" ON "messages"("created_at");

-- CreateIndex
CREATE INDEX "external_llm_configs_owner_id_idx" ON "external_llm_configs"("owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "billing_configs_owner_id_key" ON "billing_configs"("owner_id");

-- CreateIndex
CREATE INDEX "sync_logs_source_instance_id_idx" ON "sync_logs"("source_instance_id");

-- CreateIndex
CREATE INDEX "sync_logs_target_instance_id_idx" ON "sync_logs"("target_instance_id");

-- AddForeignKey
ALTER TABLE "model_instances" ADD CONSTRAINT "model_instances_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "knowledge_entries" ADD CONSTRAINT "knowledge_entries_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "access_rules" ADD CONSTRAINT "access_rules_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "conversation_threads" ADD CONSTRAINT "conversation_threads_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "messages" ADD CONSTRAINT "messages_thread_id_fkey" FOREIGN KEY ("thread_id") REFERENCES "conversation_threads"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "external_llm_configs" ADD CONSTRAINT "external_llm_configs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "billing_configs" ADD CONSTRAINT "billing_configs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sync_logs" ADD CONSTRAINT "sync_logs_source_instance_id_fkey" FOREIGN KEY ("source_instance_id") REFERENCES "model_instances"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sync_logs" ADD CONSTRAINT "sync_logs_target_instance_id_fkey" FOREIGN KEY ("target_instance_id") REFERENCES "model_instances"("id") ON DELETE CASCADE ON UPDATE CASCADE;
