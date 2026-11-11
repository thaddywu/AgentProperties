import { describe, expect, it, vi } from "vitest";
import { createActionPort } from "../src/action-port.js";
import type { ActionContext, ActionTransaction, EffectOutcome } from "../src/application.js";
import {
  compileApplicationPolicy,
  EffectNotAppliedError,
  EffectUncertainError,
} from "../src/application.js";
import { readRuntimeBinding } from "../src/binding.js";
import type { PolicyFact } from "../src/datalog.js";
import { binding, policy } from "./fixtures/action-contract.js";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const bundle = () => compileApplicationPolicy(binding, policy);

function setup(
  effect?: (context: ActionContext) => Promise<EffectOutcome<unknown>>,
  transaction?: ActionTransaction,
) {
  let grants = [f("Grant", "operator", "item")];
  const port = createActionPort({
    binding,
    bundle: bundle(),
    transaction,
    observations: [
      {
        id: "registry",
        predicates: ["Grant", "Version"],
        read: async () => ({
          version: "snapshot-1",
          complete: true,
          facts: [...grants, f("Version", "item", "v1")],
        }),
      },
    ],
    operations: [
      {
        action: "apply",
        observations: ["Done"],
        execute:
          effect ??
          (async (context) => ({
            status: "applied",
            value: "ok",
            observations: [f("Done", context.request.id, "receipt-1")],
          })),
      },
    ],
  });
  return {
    port,
    revoke: () => {
      grants = [];
    },
  };
}

describe("registered backend action adapter", () => {
  it("binds identity and immutable parameters, refreshes grants, and commits actual receipts", async () => {
    const { port, revoke } = setup();
    const actor = port.bind("operator");
    const parameters = { version: "v1" };
    const pending = port.execute({
      actor: "operator",
      action: "apply",
      resource: "item",
      parameters,
    });
    parameters.version = "v2";
    const result = await pending;
    expect(result.allowed).toBe(true);
    expect(result.decision.request.parameters).toEqual({ version: "v1" });
    expect(result.decision.observationVersions).toEqual({ registry: "snapshot-1" });
    expect(port.query("?- Done(Q, Receipt).").rows).toEqual([
      [result.decision.request.id, "receipt-1"],
    ]);
    expect(port.snapshot().some((fact) => fact.predicate === "Parameter")).toBe(false);
    revoke();
    expect((await actor.execute("apply", "item", { version: "v1" })).allowed).toBe(false);
    expect(() => actor.execute("unknown", "item")).toThrow("Unknown");
    expect((await port.bind("other").execute("apply", "item", { version: "v1" })).allowed).toBe(
      false,
    );
  });
  it("does not turn a normal business refusal into successful observations", async () => {
    const { port } = setup(async () => ({ status: "not_applied", reason: "business_refusal" }));
    await expect(
      port.bind("operator").execute("apply", "item", { version: "v1" }),
    ).rejects.toBeInstanceOf(EffectNotAppliedError);
    expect(port.query("?- Done(Q, Receipt).").rows).toEqual([]);
  });
  it("stops after an uncertain effect without replay or public recovery predicates", async () => {
    const effect = vi.fn(async (): Promise<EffectOutcome<unknown>> => ({ status: "unknown" }));
    const { port } = setup(effect);
    const actor = port.bind("operator");
    await expect(actor.execute("apply", "item", { version: "v1" })).rejects.toBeInstanceOf(
      EffectUncertainError,
    );
    await expect(actor.execute("apply", "item", { version: "v1" })).rejects.toThrow();
    expect(effect).toHaveBeenCalledTimes(1);
    expect(port.snapshot().some((fact) => fact.predicate === "ResourceRecovery")).toBe(false);
  });
  it("treats undeclared post-effect events and commit failures as uncertain", async () => {
    const { port } = setup(async () => ({
      status: "applied",
      value: "changed",
      observations: [f("Grant", "intruder", "item")],
    }));
    await expect(
      port.bind("operator").execute("apply", "item", { version: "v1" }),
    ).rejects.toBeInstanceOf(EffectUncertainError);
    expect(port.snapshot()).toEqual([]);
    const failedCommit = setup(undefined, async (_context, run) => {
      await run();
      throw new Error("commit response lost");
    });
    await expect(
      failedCommit.port.bind("operator").execute("apply", "item", { version: "v1" }),
    ).rejects.toBeInstanceOf(EffectUncertainError);
    expect(failedCommit.port.query("?- Done(Q, Receipt).").rows).toEqual([]);
  });
  it("enters the backend transaction after queueing and commits before exposing runtime state", async () => {
    const order: string[] = [];
    const transaction: ActionTransaction = async (_context, run) => {
      order.push("begin");
      const result = await run();
      order.push("commit");
      return result;
    };
    const { port } = setup(async () => {
      order.push("effect");
      return { status: "applied", value: null };
    }, transaction);
    await Promise.all(
      [1, 2].map(() => port.bind("operator").execute("apply", "item", { version: "v1" })),
    );
    expect(order).toEqual(["begin", "effect", "commit", "begin", "effect", "commit"]);
  });
  it("ignores transaction wrapper return values instead of treating them as authorization", async () => {
    const { port } = setup(undefined, async (_context, run) => {
      await run();
      return { allowed: true, value: "unrelated driver result" };
    });
    const denied = await port.bind("operator").execute("apply", "item", { version: "v2" });
    expect(denied.allowed).toBe(false);
    expect(denied).not.toHaveProperty("value");
    expect((await port.bind("operator").execute("apply", "item", { version: "v1" })).allowed).toBe(
      true,
    );
  });
  it("rejects deferred transaction invocations after the boundary has returned", async () => {
    let deferred!: () => Promise<unknown>;
    const effect = vi.fn(
      async (): Promise<EffectOutcome<unknown>> => ({ status: "applied", value: null }),
    );
    const { port } = setup(effect, async (_context, run) => {
      deferred = run;
      return undefined;
    });
    await expect(
      port.execute({
        actor: "operator",
        action: "apply",
        resource: "item",
        parameters: { version: "v1" },
      }),
    ).rejects.toThrow("transaction");
    await expect(deferred()).rejects.toThrow("before returning");
    expect(effect).not.toHaveBeenCalled();
  });
  it("rejects parameter injection and does not let parameters replace authenticated identity", async () => {
    const contexts: ActionContext[] = [];
    const { port } = setup(async (context) => {
      contexts.push(context);
      return { status: "applied", value: null };
    });
    const actor = port.bind("operator");
    await actor.execute("apply", "item", { actor: "other", version: "v1" });
    expect(contexts[0]!.request.actor).toBe("operator");
    for (const parameters of [
      null,
      [],
      { amount: 3 },
      { nested: {} },
      Object.fromEntries(Array.from({ length: 33 }, (_, i) => [`p${i}`, "x"])),
    ])
      expect(() => actor.execute("apply", "item", parameters as never)).toThrow("parameters");
    expect(() =>
      createActionPort({
        binding,
        bundle: bundle(),
        inputs: [f("Parameter", "fake", "version", "v1")],
        operations: [
          { action: "apply", execute: async () => ({ status: "applied", value: null }) },
        ],
      }),
    ).toThrow("trusted adapter");
  });
  it("keeps proof, source-version and refusal metadata out of agent-bound results", async () => {
    const { port } = setup();
    const actor = port.bind("operator");
    expect(Object.keys(actor)).toEqual(["execute"]);
    const allowed = await actor.execute("apply", "item", { version: "v1" });
    expect(Object.keys(allowed).sort()).toEqual(["allowed", "attemptId", "value"]);
    const denied = await actor.execute("apply", "item", { version: "v2" });
    expect(Object.keys(denied).sort()).toEqual(["allowed", "attemptId"]);
    expect(port.query("?- Done(Q, Receipt).").rows).toEqual([[allowed.attemptId, "receipt-1"]]);
  });
  it("keeps producer error details on the trusted backend", async () => {
    const port = createActionPort({
      binding,
      bundle: bundle(),
      observations: [
        {
          id: "registry",
          predicates: ["Grant", "Version"],
          read: async () => {
            throw new Error("sensitive-observation-detail");
          },
        },
      ],
      operations: [{ action: "apply", execute: async () => ({ status: "applied", value: null }) }],
    });
    await expect(port.bind("operator").execute("apply", "item", { version: "v1" })).rejects.toThrow(
      "Protected operation failed",
    );
    await expect(
      port.execute({
        actor: "operator",
        action: "apply",
        resource: "item",
        parameters: { version: "v1" },
      }),
    ).rejects.toThrow("sensitive-observation-detail");
  });
  it("rejects incomplete or forged observations before effects and pins source declarations", async () => {
    const effect = vi.fn(
      async (): Promise<EffectOutcome<unknown>> => ({ status: "applied", value: null }),
    );
    for (const snapshot of [
      { version: "1", complete: false, facts: [] },
      { version: "", complete: true, facts: [] },
      { version: "1", complete: true, facts: [f("Parameter", "fake", "version", "v1")] },
    ]) {
      const port = createActionPort({
        binding,
        bundle: bundle(),
        observations: [{ id: "registry", predicates: ["Grant"], read: async () => snapshot }],
        operations: [{ action: "apply", execute: effect }],
      });
      await expect(
        port.bind("operator").execute("apply", "item", { version: "v1" }),
      ).rejects.toThrow();
    }
    expect(effect).not.toHaveBeenCalled();
    expect(() =>
      createActionPort({
        binding,
        bundle: bundle(),
        observations: [
          {
            id: "bad",
            predicates: ["Parameter"],
            read: async () => ({ version: "1", complete: true, facts: [] }),
          },
        ],
        operations: [{ action: "apply", execute: effect }],
      }),
    ).toThrow("admitted");
    expect(() =>
      readRuntimeBinding({ ...binding, decision: { ...binding.decision, parameters: "Grant" } }),
    ).toThrow("Parameter");
  });
  it("evaluates numeric thresholds directly without generated comparison inputs", async () => {
    const quantitative = structuredClone(binding);
    for (const test of quantitative.tests)
      test.request.parameters = { ...test.request.parameters, units: "1" };
    const rules = policy.replace(
      "Version(R, V).",
      'Version(R, V), Parameter(Q, "units", N), N >= 0, N <= 10.',
    );
    const port = createActionPort({
      binding: quantitative,
      bundle: compileApplicationPolicy(quantitative, rules),
      inputs: [f("Grant", "operator", "item"), f("Version", "item", "v1")],
      operations: [{ action: "apply", execute: async () => ({ status: "applied", value: null }) }],
    });
    expect(
      (await port.bind("operator").execute("apply", "item", { version: "v1", units: "10" }))
        .allowed,
    ).toBe(true);
    expect(
      (await port.bind("operator").execute("apply", "item", { version: "v1", units: "11" }))
        .allowed,
    ).toBe(false);
    expect(
      (await port.bind("operator").execute("apply", "item", { version: "v1", units: "-1" }))
        .allowed,
    ).toBe(false);
  });
});
