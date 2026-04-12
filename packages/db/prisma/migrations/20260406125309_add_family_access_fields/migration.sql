/*
  Warnings:

  - Added the required column `updated_at` to the `access_rules` table without a default value. This is not possible if the table is not empty.

*/
-- CreateEnum
CREATE TYPE "LegacyTriggerType" AS ENUM ('manual', 'inactivity', 'trusted_person');

-- AlterTable
ALTER TABLE "access_rules" ADD COLUMN     "template_name" TEXT,
ADD COLUMN     "time_restrictions" JSONB,
ADD COLUMN     "topic_restrictions" JSONB,
ADD COLUMN     "updated_at" TIMESTAMP(3) NOT NULL;

-- CreateTable
CREATE TABLE "family_invites" (
    "id" TEXT NOT NULL,
    "rule_id" TEXT NOT NULL,
    "token_hash" TEXT NOT NULL,
    "is_reusable" BOOLEAN NOT NULL DEFAULT false,
    "uses_remaining" INTEGER NOT NULL DEFAULT 1,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "family_invites_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "legacy_configs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "trigger_type" "LegacyTriggerType" NOT NULL DEFAULT 'manual',
    "inactivity_days" INTEGER NOT NULL DEFAULT 365,
    "trusted_person_rule_id" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT false,
    "activated_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "legacy_configs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "family_invites_rule_id_idx" ON "family_invites"("rule_id");

-- CreateIndex
CREATE UNIQUE INDEX "legacy_configs_owner_id_key" ON "legacy_configs"("owner_id");

-- AddForeignKey
ALTER TABLE "family_invites" ADD CONSTRAINT "family_invites_rule_id_fkey" FOREIGN KEY ("rule_id") REFERENCES "access_rules"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "legacy_configs" ADD CONSTRAINT "legacy_configs_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "owners"("id") ON DELETE CASCADE ON UPDATE CASCADE;
