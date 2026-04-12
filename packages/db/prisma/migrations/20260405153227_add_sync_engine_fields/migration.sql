-- CreateEnum
CREATE TYPE "SyncType" AS ENUM ('full', 'incremental', 'model_weights');

-- CreateEnum
CREATE TYPE "ConflictResolution" AS ENUM ('keep_source', 'keep_target', 'keep_both', 'pending');

-- AlterTable
ALTER TABLE "sync_logs" ADD COLUMN     "bytes_transferred" BIGINT NOT NULL DEFAULT 0,
ADD COLUMN     "error_message" TEXT,
ADD COLUMN     "sync_type" "SyncType" NOT NULL DEFAULT 'full',
ADD COLUMN     "total_bytes" BIGINT NOT NULL DEFAULT 0,
ADD COLUMN     "total_entries" INTEGER NOT NULL DEFAULT 0;

-- CreateTable
CREATE TABLE "sync_conflicts" (
    "id" TEXT NOT NULL,
    "sync_log_id" TEXT NOT NULL,
    "entry_id" TEXT NOT NULL,
    "entry_type" TEXT NOT NULL,
    "source_data" JSONB NOT NULL,
    "target_data" JSONB NOT NULL,
    "resolution" "ConflictResolution" NOT NULL DEFAULT 'pending',
    "resolved_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "sync_conflicts_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "sync_conflicts_sync_log_id_idx" ON "sync_conflicts"("sync_log_id");

-- CreateIndex
CREATE INDEX "sync_conflicts_entry_id_idx" ON "sync_conflicts"("entry_id");

-- AddForeignKey
ALTER TABLE "sync_conflicts" ADD CONSTRAINT "sync_conflicts_sync_log_id_fkey" FOREIGN KEY ("sync_log_id") REFERENCES "sync_logs"("id") ON DELETE CASCADE ON UPDATE CASCADE;
