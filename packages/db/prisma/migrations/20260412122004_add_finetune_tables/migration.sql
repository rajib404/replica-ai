-- CreateTable
CREATE TABLE "finetune_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "auto_approve" BOOLEAN NOT NULL DEFAULT false,
    "auto_trigger_enabled" BOOLEAN NOT NULL DEFAULT false,
    "base_model" TEXT NOT NULL DEFAULT 'mistral:7b-instruct',
    "trigger_message_count" INTEGER NOT NULL DEFAULT 500,
    "last_trigger_message_total" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "finetune_configs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "model_versions" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "model_name" TEXT NOT NULL,
    "base_model" TEXT NOT NULL,
    "training_data_path" TEXT,
    "training_pair_count" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "is_active" BOOLEAN NOT NULL DEFAULT false,
    "progress" JSONB,
    "metrics" JSONB,
    "error_message" TEXT,
    "started_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completed_at" TIMESTAMP(3),

    CONSTRAINT "model_versions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "finetune_configs_owner_id_key" ON "finetune_configs"("owner_id");

-- CreateIndex
CREATE INDEX "model_versions_owner_id_idx" ON "model_versions"("owner_id");

-- CreateIndex
CREATE INDEX "model_versions_owner_id_is_active_idx" ON "model_versions"("owner_id", "is_active");

-- AddForeignKey
ALTER TABLE "finetune_configs" ADD CONSTRAINT "finetune_configs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "model_versions" ADD CONSTRAINT "model_versions_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;
