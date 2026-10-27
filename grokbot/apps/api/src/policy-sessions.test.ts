import { randomUUID } from "node:crypto";
import { bootstrapUserSpace, createDb } from "@rakazo/db";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { advancePolicySession, createPolicySession, getPolicySession } from "./policy-sessions.js";
import type { RouterDeps } from "./router.js";

const enabled = process.env.VERIFY_DATABASE === "1" && Boolean(process.env.DATABASE_URL);
describe.skipIf(!enabled)("policy session persistence", () => {
  let db: ReturnType<typeof createDb>;
  let deps: RouterDeps;
  const userId = randomUUID();
  let actor: { userId: string; spaceId: string };
  beforeAll(async () => {
    db = createDb(process.env.DATABASE_URL!);
    deps = { prisma: db.prisma } as RouterDeps;
    await db.prisma.user.create({
      data: { id: userId, name: "Policy Test", email: `${userId}@rakazo.test` },
    });
    const { spaceId } = await bootstrapUserSpace(
      db.prisma,
      { id: userId },
      { signupsEnabled: "true", signupAllowlist: undefined },
      { claimDeploymentOwner: false },
    );
    actor = { userId, spaceId };
  });
  afterAll(async () => {
    if (!db) return;
    if (actor) {
      const space = await db.prisma.space.findUnique({ where: { id: actor.spaceId } });
      if (space) await db.prisma.organization.delete({ where: { id: space.organizationId } });
    }
    await db.prisma.user.deleteMany({ where: { id: userId } });
    await db.prisma.$disconnect();
    await db.pool.end();
  });
  it("serializes duplicates, rolls back failed generations, persists denial and scopes access", async () => {
    let session = await createPolicySession(deps, actor);
    const revisions = await Promise.all(
      [0, 0].map((revision) => advancePolicySession(deps, actor, session.id, revision)),
    );
    expect(revisions.map((s) => s.revision)).toEqual([1, 1]);
    session = revisions[0]!;
    while (session.state.phase < 4)
      session = await advancePolicySession(deps, actor, session.id, session.revision);
    await expect(
      advancePolicySession(deps, actor, session.id, session.revision, async () => {
        throw new Error("provider failed");
      }),
    ).rejects.toThrow("no state was committed");
    expect(await getPolicySession(deps, actor, session.id)).toEqual(session);
    while (session.state.phase < 11)
      session = await advancePolicySession(deps, actor, session.id, session.revision, async () => ({
        text: "Offline generated response",
        model: "test",
      }));
    const denied = session.state.events.filter((e) => e.decision === "deny");
    expect(denied).toHaveLength(1);
    expect(denied[0]!.after).toEqual(denied[0]!.before);
    expect(session.state.local.auditor_a.artifacts).not.toContain("reply_hiring");
    expect(await getPolicySession(deps, actor, session.id)).toEqual(session);
    await expect(
      getPolicySession(deps, { ...actor, userId: "another-user" }, session.id),
    ).rejects.toThrow();
    await expect(
      advancePolicySession(
        deps,
        { ...actor, spaceId: "another-space" },
        session.id,
        session.revision,
      ),
    ).rejects.toThrow();
  });
});
