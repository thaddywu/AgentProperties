import { randomUUID } from "node:crypto";
import type { AgentRunRequest, AgentRuntime } from "@rakazo/adapter-kit";
import type { ExecutorDeps, NativePolicyExecution } from "@rakazo/adapters";
import { continueNativePolicyRun, initializeNativePolicy } from "@rakazo/adapters";
import type { PolicyPrincipal } from "@rakazo/contracts";
import { PolicyState } from "@rakazo/contracts";
import type { Prisma } from "@rakazo/db";
import { bootstrapUserSpace, createDb, selectSpaceModelPreference } from "@rakazo/db";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { enableNativePolicy } from "./native-policy.js";
import type { RouterDeps } from "./router.js";

const enabled = process.env.VERIFY_DATABASE === "1" && Boolean(process.env.DATABASE_URL);
describe.skipIf(!enabled)("native policy message path", () => {
  let db: ReturnType<typeof createDb>;
  let originalSpaceId: string;
  let spaceId: string;
  let sessionId: string;
  let bots: Record<PolicyPrincipal, string>;
  const userId = randomUUID();
  const observed: AgentRunRequest[] = [];
  let forbidden = false;
  const runtime: AgentRuntime = {
    kind: "scripted",
    async *run(request) {
      observed.push(request);
      if (forbidden) {
        await request.executeTool!("shell", { command: "true" });
        return;
      }
      const inputs = JSON.parse(request.prompt) as { id: string; text: string }[];
      const own = (Object.keys(bots) as PolicyPrincipal[]).find((p) => bots[p] === request.botId)!;
      if (own === "auditor_a") {
        if (!inputs.some((a) => a.id.startsWith("output_"))) {
          for (const dept of ["procurement", "facility", "hiring"] as const)
            await request.executeTool!("message_bot", {
              bot_id: bots[dept],
              message: `Please send ${dept} budget.`,
            });
        } else if (
          inputs.some((a) => a.text.includes("was blocked")) &&
          !inputs.some((a) => a.text === "Audit incomplete.")
        ) {
          await request.executeTool!("message_bot", {
            bot_id: bots.board,
            message: "Audit incomplete.",
          });
        }
      } else if (own !== "board") {
        await request.executeTool!("message_bot", {
          bot_id: "auditor_a",
          message: `${own} budget amount.`,
        });
      }
      yield { type: "done", text: "Turn finished." };
    },
    abort: async () => {},
  };
  let deps: ExecutorDeps;
  beforeAll(async () => {
    db = createDb(process.env.DATABASE_URL!);
    await db.prisma.user.create({
      data: { id: userId, email: `${userId}@rakazo.test`, name: "Native policy test" },
    });
    const setup = await bootstrapUserSpace(
      db.prisma,
      { id: userId },
      { signupsEnabled: "true", signupAllowlist: undefined },
      { claimDeploymentOwner: false },
    );
    originalSpaceId = setup.spaceId;
    const credential = await db.prisma.userModelCredential.create({
      data: { userId, provider: "test", label: "offline", secretId: "unused" },
    });
    await selectSpaceModelPreference(
      db.prisma,
      { userId, spaceId: originalSpaceId },
      credential.id,
      "offline",
    );
    const context = await enableNativePolicy({ prisma: db.prisma } as RouterDeps, {
      userId,
      spaceId: originalSpaceId,
    });
    spaceId = context.policySpaceId!;
    sessionId = context.sessionId!;
    bots = context.bots as typeof bots;
    deps = {
      prisma: db.prisma,
      runtime,
      events: { notify: vi.fn(), append: vi.fn() },
      jobs: { enqueue: vi.fn() },
    } as unknown as ExecutorDeps;
    await db.prisma.$transaction(async (tx) => {
      const row = await tx.policySession.findUniqueOrThrow({ where: { id: sessionId } });
      const state = PolicyState.parse(row.state);
      const ctx: NativePolicyExecution = {
        tx,
        state,
        sessionId,
        spaceId,
        userId,
        bots,
        queued: [],
      };
      await initializeNativePolicy(ctx);
      await tx.policySession.update({
        where: { id: sessionId },
        data: { state: state as unknown as Prisma.InputJsonValue },
      });
    });
  });
  afterAll(async () => {
    if (!db) return;
    const space = await db.prisma.space.findUnique({ where: { id: originalSpaceId } });
    if (space) await db.prisma.organization.delete({ where: { id: space.organizationId } });
    await db.prisma.user.deleteMany({ where: { id: userId } });
    await db.prisma.$disconnect();
    await db.pool.end();
  });
  async function execute(id: string) {
    const run = await db.prisma.run.update({
      where: { id },
      data: { status: "running", leaseOwner: "test", leaseFence: 1 },
    });
    expect(
      await continueNativePolicyRun(deps, run, "test", 1, async () => ({
        provider: "test",
        id: "offline",
      })),
    ).toBe(true);
  }
  it("uses native tasks and receipts while keeping denied content out of recipient history and model inputs", async () => {
    for (let count = 0; count < 15; count++) {
      const run = await db.prisma.run.findFirst({
        where: { spaceId, status: "queued" },
        orderBy: { createdAt: "asc" },
      });
      if (!run) break;
      await execute(run.id);
    }
    expect(await db.prisma.run.count({ where: { spaceId, status: "failed" } })).toBe(0);
    const row = await db.prisma.policySession.findUniqueOrThrow({ where: { id: sessionId } });
    const state = PolicyState.parse(row.state);
    const deny = state.events.filter((e) => e.decision === "deny");
    expect(deny).toHaveLength(1);
    expect(deny[0]!.rules).toContain("R3c");
    expect(deny[0]!.before).toEqual(deny[0]!.after);
    const blocked = state.artifacts[deny[0]!.artifactId]!;
    expect(state.local.auditor_a.artifacts).not.toContain(blocked.id);
    const thread = await db.prisma.thread.findUniqueOrThrow({ where: { botId: bots.auditor_a } });
    const messages = await db.prisma.message.findMany({ where: { threadId: thread.id } });
    expect(messages.some((m) => JSON.stringify(m.blocks).includes(blocked.text))).toBe(false);
    expect(messages.some((m) => m.policy !== null)).toBe(true);
    for (const request of observed) {
      expect(request.tools.map((t) => t.name)).toEqual(["message_bot"]);
      expect(request.useBuiltinTools).toBe(false);
      expect(request.history).toEqual([]);
      if (request.botId === bots.auditor_a) expect(request.prompt).not.toContain(blocked.text);
    }
    expect(
      state.local.board.artifacts.some((id) => state.artifacts[id]!.text === "Audit incomplete."),
    ).toBe(true);
  });
  it("rejects a forbidden tool even if a runtime tries to call it, rolling back the turn", async () => {
    forbidden = true;
    const thread = await db.prisma.thread.findUniqueOrThrow({ where: { botId: bots.board } });
    const task = await db.prisma.task.create({
      data: {
        userId,
        spaceId,
        botId: bots.board,
        threadId: thread.id,
        prompt: "Attempt a tool",
        status: "queued",
      },
    });
    const run = await db.prisma.run.create({
      data: {
        userId,
        spaceId,
        botId: bots.board,
        threadId: thread.id,
        taskId: task.id,
        status: "queued",
        trigger: "manual",
      },
    });
    const before = await db.prisma.policySession.findUniqueOrThrow({ where: { id: sessionId } });
    const count = await db.prisma.message.count({ where: { threadId: thread.id } });
    await execute(run.id);
    expect((await db.prisma.run.findUniqueOrThrow({ where: { id: run.id } })).status).toBe(
      "failed",
    );
    expect(
      (await db.prisma.policySession.findUniqueOrThrow({ where: { id: sessionId } })).state,
    ).toEqual(before.state);
    expect(await db.prisma.message.count({ where: { threadId: thread.id } })).toBe(count);
  });
});
