-- CreateTable
CREATE TABLE "learning_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "auto_topics" JSONB NOT NULL DEFAULT '[]',
    "ignore_topics" JSONB NOT NULL DEFAULT '[]',
    "depth" TEXT NOT NULL DEFAULT 'moderate',
    "schedule_hour_utc" INTEGER NOT NULL DEFAULT 3,
    "max_daily_web_searches" INTEGER NOT NULL DEFAULT 10,
    "use_external_llm" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "learning_configs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "learning_logs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "topic" TEXT NOT NULL,
    "depth" TEXT NOT NULL DEFAULT 'moderate',
    "sources_used" JSONB NOT NULL DEFAULT '[]',
    "entries_created" INTEGER NOT NULL DEFAULT 0,
    "summary" TEXT,
    "status" TEXT NOT NULL DEFAULT 'completed',
    "error_message" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "learning_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_logs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT,
    "actor_id" TEXT,
    "actor_role" TEXT,
    "action" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "resource_type" TEXT,
    "resource_id" TEXT,
    "outcome" TEXT NOT NULL DEFAULT 'success',
    "ip_address" TEXT,
    "user_agent" TEXT,
    "request_id" TEXT,
    "details" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "two_factor_auth" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "secret_encrypted" TEXT NOT NULL,
    "backup_codes_encrypted" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "confirmed_at" TIMESTAMP(3),
    "last_used_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "two_factor_auth_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "data_export_requests" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "archive_path" TEXT,
    "archive_size_bytes" BIGINT,
    "archive_sha256" TEXT,
    "error_message" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completed_at" TIMESTAMP(3),
    "expires_at" TIMESTAMP(3),
    "downloaded_at" TIMESTAMP(3),

    CONSTRAINT "data_export_requests_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "learning_configs_owner_id_key" ON "learning_configs"("owner_id");

-- CreateIndex
CREATE INDEX "learning_logs_owner_id_idx" ON "learning_logs"("owner_id");

-- CreateIndex
CREATE INDEX "learning_logs_created_at_idx" ON "learning_logs"("created_at");

-- CreateIndex
CREATE INDEX "audit_logs_owner_id_idx" ON "audit_logs"("owner_id");

-- CreateIndex
CREATE INDEX "audit_logs_action_idx" ON "audit_logs"("action");

-- CreateIndex
CREATE INDEX "audit_logs_category_idx" ON "audit_logs"("category");

-- CreateIndex
CREATE INDEX "audit_logs_created_at_idx" ON "audit_logs"("created_at");

-- CreateIndex
CREATE UNIQUE INDEX "two_factor_auth_owner_id_key" ON "two_factor_auth"("owner_id");

-- CreateIndex
CREATE INDEX "data_export_requests_owner_id_idx" ON "data_export_requests"("owner_id");
