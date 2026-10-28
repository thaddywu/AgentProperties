import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { compileApplicationPolicy, createPolicySession } from "../src/application.js";
import { readRuntimeBinding } from "../src/binding.js";

const binding = readRuntimeBinding(
  JSON.parse(
    readFileSync(new URL("../../apps/document-vault/runtime.json", import.meta.url), "utf8"),
  ),
);
// Handwritten test oracle, never an application fallback or model input.
const source = `
Accessible(A, D) :- Actor(A), Public(D), not Suspended(A).
Accessible(A, D) :- Actor(A), Confidential(D), Reader(A, D), Role(A, "reviewer"), not Suspended(A).
Allow(R) :- Request(R, A, "read", D), Accessible(A, D).
Deny(R, "suspended") :- Request(R, A, X, D), Suspended(A).
`;
const inputs = [
  { predicate: "Actor", args: ["visitor"] },
  { predicate: "Public", args: ["guide"] },
];
const request = { actor: "visitor", action: "read", resource: "guide" };
const bundle = () => compileApplicationPolicy(binding, source);

describe("application-neutral policy boundary", () => {
  it("stops an expensive request-dependent rule before calling the business effect", async () => {
    const extended = structuredClone(binding);
    extended.predicates.Token = {
      kind: "input",
      args: ["Value"],
      meaning: "Synthetic bounded-input stress case.",
    };
    extended.predicates.Pair = {
      kind: "derived",
      args: ["Left", "Right"],
      meaning: "Synthetic cross product.",
    };
    const expensive = `${source}\nPair(X, Y) :- Request(R, A, Op, D), Token(X), Token(Y).`;
    const session = createPolicySession(extended, compileApplicationPolicy(extended, expensive), [
      ...inputs,
      ...Array.from({ length: 120 }, (_, i) => ({ predicate: "Token", args: [String(i)] })),
    ]);
    const effect = vi.fn(async () => "body");
    await expect(session.execute(request, effect)).rejects.toThrow("limit exceeded");
    expect(effect).not.toHaveBeenCalled();
    expect(session.snapshot()).toHaveLength(122);
  });
  it("bounds explanations even when a small proof DAG expands exponentially", () => {
    const extended = structuredClone(binding);
    let expanded = source;
    for (let i = 0; i < 24; i++) {
      extended.predicates[`Level${i}`] = {
        kind: "derived",
        args: ["Actor"],
        meaning: "Test dependency.",
      };
      expanded +=
        i === 0
          ? "\nLevel0(A) :- Actor(A)."
          : `\nLevel${i}(A) :- Level${i - 1}(A), Level${i - 1}(A).`;
    }
    const session = createPolicySession(
      extended,
      compileApplicationPolicy(extended, expanded),
      inputs,
    );
    const proof = JSON.stringify(session.why({ predicate: "Level23", args: ["visitor"] }));
    expect(proof).toContain('"truncated":true');
    expect(proof.length).toBeLessThan(100_000);
  });
  it("validates independent cases and executes the actual callback only on allow", async () => {
    const session = createPolicySession(binding, bundle(), inputs);
    const effect = vi.fn(async () => "body");
    const denied = await session.execute({ ...request, resource: "secret" }, effect);
    expect(denied.allowed).toBe(false);
    expect(denied).not.toHaveProperty("value");
    expect(effect).not.toHaveBeenCalled();
    expect(denied.decision.reasons).toEqual(["no_explicit_allow"]);
    const allowed = await session.execute(request, effect, [
      { predicate: "Read", args: ["visitor", "guide"] },
    ]);
    expect(allowed.allowed && allowed.value).toBe("body");
    expect(effect).toHaveBeenCalledTimes(1);
    expect(session.snapshot().filter((fact) => fact.predicate === "Read")).toHaveLength(1);
    expect(session.snapshot().some((fact) => fact.predicate === "Request")).toBe(false);
  });
  it("gives deny precedence over allow and explains the decision", () => {
    const conflict = source.replace("Actor(A), Public(D), not Suspended(A)", "Actor(A), Public(D)");
    const session = createPolicySession(binding, compileApplicationPolicy(binding, conflict), [
      ...inputs,
      { predicate: "Suspended", args: ["visitor"] },
    ]);
    const decision = session.check(request);
    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toEqual(["suspended"]);
    expect(decision.evidence.map((proof) => proof.fact.predicate).sort()).toEqual([
      "Allow",
      "Deny",
    ]);
  });
  it("shares one policy across query, why, what-if and the real gate, without committing hypotheticals", () => {
    const session = createPolicySession(binding, bundle(), inputs);
    expect(session.query("?- Accessible(A, D).").rows).toEqual([["visitor", "guide"]]);
    expect(
      session
        .why({ predicate: "Accessible", args: ["visitor", "guide"] })
        ?.premises.map((proof) => proof.fact.predicate),
    ).toContain("Public");
    expect(
      session.whatIf(request, [...inputs, { predicate: "Suspended", args: ["visitor"] }]).allowed,
    ).toBe(false);
    expect(session.check(request).allowed).toBe(true);
    expect(() => session.query('Suspended("visitor"). ?- Accessible(A, D).')).toThrow("read-only");
  });
  it("rejects schema, input-head, unsafe, negative-cycle, directive and query attacks", () => {
    for (const bad of [
      "Unknown(A) :- Actor(A).",
      "Allow(A, B) :- Actor(A), Public(B).",
      'Role(A, "reviewer") :- Actor(A).',
      "Allow(A) :- not Suspended(A).",
      "Accessible(A, D) :- Actor(A), Public(D), not Accessible(A, D).",
      '.include "rules.dl"',
      "?- Actor(A).",
      'Allow("fixed-id").',
    ])
      expect(() => compileApplicationPolicy(binding, bad)).toThrow();
  });
  it("detects semantic mutations with adapter-owned acceptance cases", () => {
    expect(() =>
      compileApplicationPolicy(binding, source.replace(', Role(A, "reviewer")', "")),
    ).toThrow("reader-without-role");
    expect(() => compileApplicationPolicy(binding, source.replace("Reader(A, D), ", ""))).toThrow(
      "role-without-grant",
    );
    expect(() =>
      compileApplicationPolicy(
        binding,
        source.replaceAll(", not Suspended(A)", "").replace(/Deny\(R[^\n]+/, ""),
      ),
    ).toThrow("suspended-public-reader");
  });
  it("pins the trusted binding, checks bundle integrity and snapshots mutable inputs", () => {
    const artifact = bundle();
    expect(() =>
      createPolicySession(binding, { ...artifact, source: `${source}\n// tamper` }, inputs),
    ).toThrow("hash mismatch");
    expect(() =>
      createPolicySession(
        binding,
        { ...artifact, binding: { ...binding, id: "different" } },
        inputs,
      ),
    ).toThrow("binding mismatch");
    const original = structuredClone(inputs);
    const session = createPolicySession(binding, artifact, original);
    original.push({ predicate: "Suspended", args: ["visitor"] });
    artifact.source = "broken";
    expect(session.check(request).allowed).toBe(true);
    for (const fact of [
      { predicate: "Allow", args: ["r"] },
      { predicate: "Request", args: ["r", "visitor", "read", "guide"] },
    ])
      expect(() => createPolicySession(binding, bundle(), [fact])).toThrow("trusted adapter");
  });
  it("rolls back runtime observations after callback failure and keeps the queue usable", async () => {
    const session = createPolicySession(binding, bundle(), inputs);
    await expect(
      session.execute(request, async () => {
        throw new Error("storage failed");
      }, [{ predicate: "Read", args: ["visitor", "guide"] }]),
    ).rejects.toThrow("storage failed");
    expect(session.query("?- Read(A, D).").rows).toEqual([]);
    expect((await session.execute(request, async () => "retry")).allowed).toBe(true);
  });
  it("serializes check/effect/commit so concurrent requests cannot reuse an old decision", async () => {
    const once = `${source}\nDeny(R, "already_read") :- Request(R, A, "read", D), Read(A, D).`;
    const session = createPolicySession(binding, compileApplicationPolicy(binding, once), inputs);
    expect(session.check(request).allowed).toBe(true);
    const effect = vi.fn(async () => "body");
    const reads = await Promise.all(
      [1, 2].map(() =>
        session.execute(request, effect, [{ predicate: "Read", args: ["visitor", "guide"] }]),
      ),
    );
    expect(reads.map((read) => read.allowed)).toEqual([true, false]);
    expect(effect).toHaveBeenCalledTimes(1);
    expect(session.query("?- Read(A, D).").rows).toHaveLength(1);
  });
  it("rejects invalid commits before any external effect and blocks inspection mid-operation", async () => {
    const session = createPolicySession(binding, bundle(), inputs);
    const effect = vi.fn(async () => "body");
    expect(() =>
      session.execute(request, effect, [{ predicate: "Role", args: ["bad-arity"] }]),
    ).toThrow();
    expect(effect).not.toHaveBeenCalled();
    let release!: () => void;
    const blocker = new Promise<void>((resolve) => {
      release = resolve;
    });
    const operation = session.execute(request, async () => blocker);
    expect(() => session.query("?- Public(D).")).toThrow("in-flight");
    release();
    await operation;
    expect(session.query("?- Public(D).").rows).toHaveLength(1);
  });
  it("uses different predicate names and constant escaping without any Nova vocabulary", () => {
    const renamed = structuredClone(binding);
    const names = { Request: "Attempt", Allow: "Permit", Deny: "Refuse" };
    for (const [before, after] of Object.entries(names)) {
      renamed.predicates[after] = renamed.predicates[before]!;
      delete renamed.predicates[before];
    }
    renamed.decision = { request: "Attempt", allow: "Permit", deny: "Refuse" };
    const transformed = source.replace(
      /Request|Allow|Deny/g,
      (word) => names[word as keyof typeof names],
    );
    const actor = 'UPPER"case\\name';
    const session = createPolicySession(renamed, compileApplicationPolicy(renamed, transformed), [
      { predicate: "Actor", args: [actor] },
      { predicate: "Public", args: ["Doc"] },
    ]);
    expect(session.check({ actor, action: "read", resource: "Doc" }).allowed).toBe(true);
    expect(session.query("?- Accessible(A, D).").rows).toEqual([[actor, "Doc"]]);
  });
});
