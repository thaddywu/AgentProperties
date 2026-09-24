import { ORPCError } from "@orpc/server";
import type { NativePolicyExecution } from "@rakazo/adapters";
import { flushNativePolicy, initializeNativePolicy, POLICY_NAMES } from "@rakazo/adapters";
import type { Actor, PolicyPrincipal } from "@rakazo/contracts";
import { PolicyState } from "@rakazo/contracts";
import { emptyPolicyState } from "@rakazo/core";
import type { Prisma } from "@rakazo/db";
import { createSpaceForMember } from "@rakazo/db";
import { aiConsentStatus } from "./ai-consent.js";
import type { RouterDeps } from "./router.js";

async function findSession(deps: RouterDeps, actor: Actor) {
  return deps.prisma.policySession.findFirst({
    where: {
      userId: actor.userId,
      nativeSpaceId: { not: null },
      OR: [{ spaceId: actor.spaceId }, { nativeSpaceId: actor.spaceId }],
    },
    orderBy: { createdAt: "desc" },
  });
}
export async function nativePolicyContext(deps: RouterDeps, actor: Actor) {
  const session = await findSession(deps, actor);
  return {
    enabled: session?.nativeSpaceId === actor.spaceId,
    sessionId: session?.id,
    originalSpaceId: session?.spaceId ?? actor.spaceId,
    policySpaceId: session?.nativeSpaceId ?? undefined,
    bots: (session?.nativeBots ?? {}) as Record<string, string>,
    started: session ? PolicyState.parse(session.state).phase > 0 : false,
  };
}
export async function enableNativePolicy(deps: RouterDeps, actor: Actor, fresh = false) {
  const existing = await findSession(deps, actor);
  if (existing && !fresh) return nativePolicyContext(deps, actor);
  if (existing) actor = { ...actor, spaceId: existing.spaceId };
  const space = await createSpaceForMember(deps.prisma, {
    currentSpaceId: actor.spaceId,
    userId: actor.userId,
    name: "Nova · Policy",
  });
  await deps.prisma.$transaction(async (tx) => {
    const bots: Record<string, string> = {};
    for (const [principal, name] of Object.entries(POLICY_NAMES)) {
      const bot = await tx.bot.create({
        data: {
          spaceId: space.id,
          userId: actor.userId,
          name,
          title: "Nova Budget Audit",
          description: "App 2 · message_bot only",
          color: "#64748b",
          instructions: "Nova policy principal",
          thread: { create: { spaceId: space.id, userId: actor.userId } },
        },
      });
      bots[principal] = bot.id;
    }
    await tx.policySession.create({
      data: {
        spaceId: actor.spaceId,
        userId: actor.userId,
        nativeSpaceId: space.id,
        nativeBots: bots,
        state: emptyPolicyState() as unknown as Prisma.InputJsonValue,
      },
    });
  });
  return nativePolicyContext(deps, actor);
}
export async function startNativePolicy(deps: RouterDeps, actor: Actor) {
  const session = await findSession(deps, actor);
  if (!session || session.nativeSpaceId !== actor.spaceId) throw new ORPCError("NOT_FOUND");
  // Initial model use is authorized under the originating account/space's existing consent.
  const consent = await aiConsentStatus(
    deps,
    { ...actor, spaceId: session.spaceId },
    { uses: ["model"] },
  );
  if (consent.recipients.some((r) => !r.allowed))
    throw new ORPCError("FORBIDDEN", {
      message: "Review model data sharing in Original Rakazo first.",
    });
  const queued: string[] = [];
  await deps.prisma.$transaction(
    async (tx) => {
      await tx.$queryRaw`SELECT id FROM policy_sessions WHERE id = ${session.id} FOR UPDATE`;
      const row = await tx.policySession.findUniqueOrThrow({ where: { id: session.id } });
      const state = PolicyState.parse(row.state);
      const ctx: NativePolicyExecution = {
        tx,
        state,
        bots: row.nativeBots as Record<PolicyPrincipal, string>,
        sessionId: row.id,
        spaceId: actor.spaceId,
        userId: actor.userId,
        queued,
      };
      await initializeNativePolicy(ctx);
      await tx.policySession.update({
        where: { id: row.id },
        data: { state: state as unknown as Prisma.InputJsonValue, revision: { increment: 1 } },
      });
    },
    { timeout: 15_000 },
  );
  await flushNativePolicy(deps, actor.spaceId, queued);
  return nativePolicyContext(deps, actor);
}
