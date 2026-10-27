import type { Actor } from "@rakazo/contracts";
import { emptyPolicyState } from "@rakazo/core";
import { describe, expect, it } from "vitest";
import { inspectNativePolicy, queryNativePolicy } from "./native-policy.js";
import type { RouterDeps } from "./router.js";

const actor = { userId: "observer", spaceId: "policy" } as Actor;
const state = emptyPolicyState();
state.local.board.facts.push({ predicate: "Example", args: ["value"] });
const row = { id: "session", nativeSpaceId: "policy", revision: 7, state };
const deps = (value: unknown) =>
  ({
    prisma: {
      policySession: {
        findFirst: async (args: any) => {
          expect(args.where.userId).toBe(actor.userId);
          expect(args.where.OR).toContainEqual({ nativeSpaceId: actor.spaceId });
          return value;
        },
      },
    },
  }) as unknown as RouterDeps;
const input = { revision: 7, side: "after" as const, scope: "board", program: "?- Example(X)." };
describe("policy inspector authorization and snapshots", () => {
  it("returns snapshot facts and executes a read-only program", async () => {
    const original = JSON.stringify(row);
    expect((await inspectNativePolicy(deps(row), actor)).revision).toBe(7);
    expect(await queryNativePolicy(deps(row), actor, input)).toEqual({
      columns: ["X"],
      rows: [["value"]],
    });
    expect(JSON.stringify(row)).toBe(original);
  });
  it("requires an owned session in the active native policy space", async () => {
    await expect(inspectNativePolicy(deps(null), actor)).rejects.toMatchObject({
      code: "NOT_FOUND",
    });
    await expect(
      inspectNativePolicy(deps({ ...row, nativeSpaceId: "other" }), actor),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
  });
  it("rejects stale revisions and unknown events", async () => {
    await expect(
      queryNativePolicy(deps(row), actor, { ...input, revision: 6 }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
    await expect(
      queryNativePolicy(deps(row), actor, { ...input, event: 999 }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
  });
});
