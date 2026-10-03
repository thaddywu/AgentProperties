ALTER TABLE "policy_sessions" ADD COLUMN "nativeSpaceId" TEXT, ADD COLUMN "nativeBots" JSONB;
CREATE UNIQUE INDEX "policy_sessions_nativeSpaceId_key" ON "policy_sessions"("nativeSpaceId");
ALTER TABLE "messages" ADD COLUMN "policy" JSONB;
