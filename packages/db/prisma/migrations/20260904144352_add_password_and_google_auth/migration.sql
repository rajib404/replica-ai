-- AlterTable
ALTER TABLE "owners" ADD COLUMN     "google_id" TEXT,
ADD COLUMN     "password_hash" TEXT;

-- CreateIndex
CREATE UNIQUE INDEX "owners_google_id_key" ON "owners"("google_id");
