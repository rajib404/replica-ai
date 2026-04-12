-- CreateTable
CREATE TABLE "verification_logs" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "success" BOOLEAN NOT NULL,
    "similarity_score" DOUBLE PRECISION,
    "source" TEXT NOT NULL DEFAULT 'api',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "verification_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "suspicion_events" (
    "id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "event_type" TEXT NOT NULL,
    "score_delta" INTEGER NOT NULL,
    "detail" TEXT,
    "session_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "suspicion_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "verification_logs_owner_id_idx" ON "verification_logs"("owner_id");

-- CreateIndex
CREATE INDEX "verification_logs_created_at_idx" ON "verification_logs"("created_at");

-- CreateIndex
CREATE INDEX "suspicion_events_owner_id_idx" ON "suspicion_events"("owner_id");

-- CreateIndex
CREATE INDEX "suspicion_events_created_at_idx" ON "suspicion_events"("created_at");
