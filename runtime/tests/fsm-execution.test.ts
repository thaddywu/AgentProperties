import { expect, it, vi } from "vitest";
import {
  compileApplicationPolicy,
  createPolicySession,
  EffectNotAppliedError,
  EffectUncertainError,
} from "../src/application.js";
import type { RuntimeBinding } from "../src/binding.js";
import { LIFECYCLE_PREDICATES } from "../src/lifecycle.js";

const f = (predicate: string, ...args: string[]) => ({ predicate, args });
const initial = [
  f("ResourceType", "draft", "document"),
  f("ResourceState", "draft", "draft"),
  f("AllowedTransition", "document", "approve", "draft", "approved"),
  f("AllowedTransition", "document", "publish", "approved", "published"),
];
const binding: RuntimeBinding = {
  version: 1,
  id: "fsm-documents",
  context: "Shared typed machine, current state only.",
  mechanisms: ["fsm"],
  predicates: {
    ...LIFECYCLE_PREDICATES,
    Request: { kind: "input", args: ["Q", "Principal", "EventKind"], meaning: "Request." },
    Allow: { kind: "derived", args: ["Q"], meaning: "Permission." },
    Deny: { kind: "derived", args: ["Q", "Reason"], meaning: "Refusal." },
  },
  decision: { request: "Request", allow: "Allow", deny: "Deny" },
  tests: [],
};
const rules = "Allow(Q) :- Request(Q, P, E).";
const session = () =>
  createPolicySession(binding, compileApplicationPolicy(binding, rules), initial);
const request = (action: string, resource = "draft") => ({ actor: "operator", action, resource });

it("shares machine edges by type while replacing current state without execution-history predicates", async () => {
  const runtime = session(),
    effect = vi.fn(async () => "done");
  expect(runtime.query('?- ReachableState("document", "draft", S).').rows.sort()).toEqual([
    ["approved"],
    ["published"],
  ]);
  expect((await runtime.execute(request("publish"), effect)).decision.reasons).toContain(
    "invalid_transition",
  );
  expect((await runtime.execute(request("approve"), effect)).allowed).toBe(true);
  expect((await runtime.execute(request("publish"), effect)).allowed).toBe(true);
  expect(runtime.query("?- ResourceState(R, S).").rows).toEqual([["draft", "published"]]);
  expect(effect).toHaveBeenCalledTimes(2);
  expect(runtime.snapshot().some((fact) => fact.predicate === "ActionTaken")).toBe(false);
});

it("serializes two calls so a consumed transition cannot be used twice", async () => {
  const runtime = session(),
    effect = vi.fn(async () => "done");
  const results = await Promise.all([
    runtime.execute(request("approve"), effect),
    runtime.execute(request("approve"), effect),
  ]);
  expect(results.map((result) => result.allowed)).toEqual([true, false]);
  expect(effect).toHaveBeenCalledTimes(1);
});

it("keeps machine configuration and runtime-owned state out of effect observations", async () => {
  const runtime = session();
  const initialOnly = { ...binding, fsmActions: [] };
  expect(
    createPolicySession(initialOnly, compileApplicationPolicy(initialOnly, rules), [
      f("InitialState", "document", "draft"),
    ]).query("?- InitialState(T, S).").rows,
  ).toEqual([["document", "draft"]]);
  expect(() =>
    createPolicySession(binding, compileApplicationPolicy(binding, rules), [
      ...initial,
      f("InitialState", "document", "draft"),
      f("InitialState", "document", "published"),
    ]),
  ).toThrow("initial state");
  expect(() =>
    runtime.execute(request("approve"), async () => "done", [
      f("ResourceState", "draft", "published"),
    ]),
  ).toThrow("runtime");
  await expect(
    runtime.replaceInputs([...initial, f("ResourceState", "draft", "published")]),
  ).rejects.toThrow();
  expect(() =>
    compileApplicationPolicy(
      binding,
      `${rules}\nCanTransition(R, E, A, B) :- ResourceState(R, A), AllowedTransition(T, E, A, B).`,
    ),
  ).toThrow("foundation");
});

it("certified no-effect errors leave a session usable; uncertainty stops it without reconciliation machinery", async () => {
  const runtime = session();
  await expect(
    runtime.execute(request("approve"), async () => {
      throw new EffectNotAppliedError("no write");
    }),
  ).rejects.toBeInstanceOf(EffectNotAppliedError);
  await expect(
    runtime.execute(request("approve"), async () => {
      throw new Error("response lost");
    }),
  ).rejects.toBeInstanceOf(EffectUncertainError);
  const effect = vi.fn(async () => "duplicate");
  await expect(runtime.execute(request("approve"), effect)).rejects.toThrow("session is stopped");
  expect(effect).not.toHaveBeenCalled();
  expect(runtime.snapshot().map((fact) => fact.predicate)).not.toContain("ResourceRecovery");
});
