-- AlterTable
ALTER TABLE "owners" ADD COLUMN     "family_code" TEXT;

-- CreateIndex
CREATE UNIQUE INDEX "owners_family_code_key" ON "owners"("family_code");

