import { describe, expect, it } from "vitest";
import { createMessagingProfile, createMessagingRuntime } from "../src/messaging.js";
import type { ProtocolWitness } from "../src/protocol-planner.js";
import { applyProtocolPlan, synthesizeProtocol } from "../src/protocol-planner.js";

const profile = () =>
  createMessagingProfile({
    principals: ["source", "agent", "reader"],
    sourceAuthorities: ["source"],
    configuration: [
      { predicate: "TagRequiresCapability", args: ["secret", "review"] },
      { predicate: "AgentHasCapability", args: ["agent", "review"] },
    ],
  });
function witnesses() {
  const runtime = createMessagingRuntime(profile());
  const result: ProtocolWitness[] = [];
  const capture = () =>
    result.push({
      id: `snapshot${result.length}`,
      stores: Object.fromEntries(
        Object.entries(runtime.state.stores).map(([site, rows]) => [site, rows.map((r) => r.fact)]),
      ),
    });
  runtime.send("source", "agent", "seed", "input", { tag: "secret" });
  capture();
  runtime.settle("seed");
  capture();
  runtime.send("agent", "reader", "relay", "summary");
  capture();
  runtime.settle("relay");
  capture();
  return result;
}
const search = () => ({
  profile: profile(),
  witnesses: witnesses(),
  storage: [
    {
      name: "TagRequiresCapability",
      choices: [["source"], ["agent", "reader"], ["source", "agent", "reader"]],
    },
  ],
  inference: [
    { name: "runtime-dependency", choices: [["reader"], ["agent"], ["source", "agent", "reader"]] },
  ],
});

describe("bounded distributed protocol synthesis", () => {
  it("selects the least declared cost while preserving full closure and every actual local gate", () => {
    const result = synthesizeProtocol(search());
    expect(result.plansExamined).toBe(9);
    expect(result.optimalWithinDeclaredSpace).toBe(true);
    expect(result.plan.replicateAt.TagRequiresCapability).toEqual(["agent", "reader"]);
    expect(result.plan.ruleLocations["runtime-dependency"]).toEqual(["agent"]);
    const deployed = createMessagingRuntime(applyProtocolPlan(profile(), result));
    deployed.send("source", "agent", "seed", "input", { tag: "secret" });
    expect(deployed.settle("seed").allowed).toBe(true);
    deployed.send("agent", "reader", "relay", "summary");
    expect(deployed.settle("relay").allowed).toBe(false);
    expect(deployed.accessible("reader")).toEqual([]);
    expect(deployed.query("agent", "?- Knows(A,T).").rows).toEqual([["agent", "secret"]]);
  });
  it("preserves declared local query observations as well as global facts", () => {
    const result = synthesizeProtocol({
      ...search(),
      queries: [{ owner: "source", source: "?- TagRequiresCapability(T,C)." }],
    });
    expect(result.plan.replicateAt.TagRequiresCapability).toEqual(["source", "agent", "reader"]);
    expect(result.queryObservations).toBe(1);
  });
  it("rejects private replication, unknown sites, insufficient budgets and stale-program plans", () => {
    expect(() =>
      synthesizeProtocol({
        ...search(),
        storage: [{ name: "AgentHasCapability", choices: [["reader"]] }],
      }),
    ).toThrow(/shareable/);
    expect(() =>
      synthesizeProtocol({
        ...search(),
        storage: [{ name: "TagRequiresCapability", choices: [["stranger"]] }],
      }),
    ).toThrow(/boundary/);
    expect(() => synthesizeProtocol({ ...search(), maxPlans: 1 })).toThrow(/budget/);
    const result = synthesizeProtocol(search());
    expect(() => applyProtocolPlan({ ...profile(), principals: ["different"] }, result)).toThrow(
      /another program/,
    );
    expect(() => applyProtocolPlan({ ...profile(), configuration: [] }, result)).toThrow(
      /another program/,
    );
    expect(() =>
      synthesizeProtocol({
        ...search(),
        witnesses: [
          {
            id: "forged",
            stores: {
              source: [],
              agent: [],
              reader: [{ predicate: "Knows", args: ["reader", "secret"] }],
            },
          },
        ],
      }),
    ).toThrow(/input evidence/);
  });
  it("never labels a failed preservation search an optimum", () => {
    expect(() =>
      synthesizeProtocol({
        ...search(),
        storage: [{ name: "TagRequiresCapability", choices: [["source"]] }],
        inference: [],
      }),
    ).toThrow(/No deployment/);
  });
});
