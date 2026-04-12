-- AlterTable
ALTER TABLE "model_instances" ADD COLUMN     "api_url" TEXT,
ADD COLUMN     "auth_token_hash" TEXT,
ADD COLUMN     "capabilities" JSONB,
ADD COLUMN     "is_primary" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "last_heartbeat_at" TIMESTAMP(3);
