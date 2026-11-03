import { describe, expect, it, vi } from "vitest";
import {
  compileApplicationPolicy,
  createPolicySession,
  EffectNotAppliedError,
  EffectRecoveryRequiredError,
} from "../src/application.js";
import type { RuntimeBinding } from "../src/binding.js";
import type { PolicyFact } from "../src/datalog.js";
import { LIFECYCLE_PREDICATES } from "../src/lifecycle.js";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const initial = [
  f("ResourceType", "draft", "document"),
  f("ResourceState", "draft", "draft"),
  f("Transition", "document", "approve", "draft", "approved"),
  f("Transition", "document", "publish", "approved", "published"),
  f("Role", "reviewer", "reviewer"),
  f("Role", "publisher", "publisher"),
];
const intent = (action: string, resource = "draft") => ({
  actor: action === "approve" ? "reviewer" : "publisher",
  action,
  resource,
});
const binding: RuntimeBinding = {
  version: 1,
  id: "fsm-documents",
  context: "Trusted document service with real protected operations.",
  mechanisms: ["fsm"],
  predicates: {
    ...Object.fromEntries(
      Object.entries(LIFECYCLE_PREDICATES).map(([name, schema]) => [
        name,
        { kind: schema.kind, args: [...schema.args], meaning: name },
      ]),
    ),
    Role: { kind: "input", args: ["Actor", "Role"], meaning: "Authoritative current role." },
    Request: {
      kind: "input",
      args: ["RequestId", "Actor", "Action", "Resource"],
      meaning: "Runtime attempt.",
    },
    Allow: { kind: "derived", args: ["RequestId"], meaning: "Permission." },
    Deny: { kind: "derived", args: ["RequestId", "Reason"], meaning: "Refusal." },
  },
  decision: { request: "Request", allow: "Allow", deny: "Deny" },
  tests: [
    { name: "review-draft", inputs: initial, request: intent("approve"), allowed: true },
    { name: "cannot-publish-draft", inputs: initial, request: intent("publish"), allowed: false },
  ],
};
const policy =
  'Allow(Q) :- Request(Q, A, "approve", D), Role(A, "reviewer").\nAllow(Q) :- Request(Q, A, "publish", D), Role(A, "publisher").';
const session = (extra: PolicyFact[] = []) =>
  createPolicySession(binding, compileApplicationPolicy(binding, policy), [...initial, ...extra]);

describe("protected FSM execution independent of any backend", () => {
  it("composes structural transitions and authorization using the same rules as query and proof", async () => {
    const runtime = session();
    const effect = vi.fn(async () => "done");
    const denied = await runtime.execute(intent("publish"), effect);
    expect(denied.allowed).toBe(false);
    expect(denied.decision.reasons).toContain("invalid_transition");
    expect(
      denied.decision.evidence.some(
        (p) => p.fact.predicate === "Deny" && p.rule === "invalid-transition",
      ),
    ).toBe(true);
    expect(effect).not.toHaveBeenCalled();
    expect(runtime.query('?- CanTransition("draft", Action, From, To).').rows).toEqual([
      ["approve", "draft", "approved"],
    ]);
    expect((await runtime.execute(intent("approve"), effect)).allowed).toBe(true);
    expect((await runtime.execute(intent("publish"), effect)).allowed).toBe(true);
    expect(runtime.snapshot().filter((f) => f.predicate === "ResourceState")).toEqual([
      f("ResourceState", "draft", "published"),
    ]);
    expect(runtime.snapshot().filter((f) => f.predicate === "ActionTaken")).toHaveLength(2);
    expect((await runtime.execute(intent("publish"), effect)).allowed).toBe(false);
    expect(
      (await runtime.execute(intent("publish", "missing"), effect)).decision.reasons,
    ).toContain("unknown_resource");
    expect(effect).toHaveBeenCalledTimes(2);
  });
  it("serializes actual operations so concurrent attempts cannot reuse the old state", async () => {
    const runtime = session();
    const effect = vi.fn(async () => "approved");
    const results = await Promise.all([
      runtime.execute(intent("approve"), effect),
      runtime.execute(intent("approve"), effect),
    ]);
    expect(results.map((r) => r.allowed)).toEqual([true, false]);
    expect(effect).toHaveBeenCalledTimes(1);
    expect(runtime.query("?- ActionTaken(E, R, A, From, To).").rows).toHaveLength(1);
  });
  it("keeps runtime-owned state/history immutable through policy and observation APIs", async () => {
    const runtime = session();
    const effect = vi.fn(async () => "body");
    expect(() =>
      runtime.execute(intent("approve"), effect, [f("ResourceState", "draft", "published")]),
    ).toThrow(/runtime/);
    await expect(
      runtime.replaceInputs(
        initial.map((fact) =>
          fact.predicate === "ResourceState" ? f("ResourceState", "draft", "published") : fact,
        ),
      ),
    ).rejects.toThrow(/runtime-owned/);
    expect(() =>
      compileApplicationPolicy(
        binding,
        `${policy}\nEnabledAction(R, S, A) :- ResourceState(R, S), Transition(T, A, S, To).`,
      ),
    ).toThrow(/foundation/);
    expect(() => session([f("ResourceState", "draft", "published")])).toThrow(/Conflicting/);
    const changed = initial.filter((fact) => fact.predicate !== "Role");
    await runtime.replaceInputs(changed);
    expect((await runtime.execute(intent("approve"), effect)).allowed).toBe(false);
    expect(effect).not.toHaveBeenCalled();
  });
  it("distinguishes confirmed no-effect failures from uncertain external outcomes", async () => {
    const runtime = session();
    await expect(
      runtime.execute(intent("approve"), async () => {
        throw new EffectNotAppliedError("Rejected before effect.");
      }),
    ).rejects.toBeInstanceOf(EffectNotAppliedError);
    expect(runtime.query("?- ResourceRecovery(R, Q).").rows).toEqual([]);
    let attempt = "";
    try {
      await runtime.execute(intent("approve"), async () => {
        throw new Error("Uncertain outcome.");
      });
    } catch (error) {
      expect(error).toBeInstanceOf(EffectRecoveryRequiredError);
      attempt = (error as EffectRecoveryRequiredError).attemptId;
    }
    expect(runtime.snapshot().filter((f) => f.predicate === "ActionTaken")).toEqual([]);
    expect(runtime.check(intent("approve")).reasons).toContain("recovery_required");
    await runtime.reconcile(attempt, "not_applied");
    expect(runtime.check(intent("approve")).allowed).toBe(true);
  });
  it("reconciles confirmed success without repeating the effect or discarding other resource updates", async () => {
    const runtime = session([
      f("ResourceType", "other", "document"),
      f("ResourceState", "other", "draft"),
    ]);
    let attempt = "";
    const effect = vi.fn(async () => {
      throw new Error("Response lost after write.");
    });
    try {
      await runtime.execute(intent("approve"), effect);
    } catch (error) {
      attempt = (error as EffectRecoveryRequiredError).attemptId;
    }
    await runtime.execute(intent("approve", "other"), async () => "done");
    await runtime.reconcile(attempt, "applied");
    expect(runtime.query("?- ResourceState(R, S).").rows.sort()).toEqual([
      ["draft", "approved"],
      ["other", "approved"],
    ]);
    expect(runtime.query("?- ActionTaken(E, R, A, From, To).").rows).toHaveLength(2);
    expect(effect).toHaveBeenCalledTimes(1);
    await expect(runtime.reconcile(attempt, "applied")).rejects.toThrow(/Unknown/);
  });
});
