import { expect, it } from "vitest";
import { compileApplicationPolicy, createPolicySession } from "../src/application.js";
import type { RuntimeBinding } from "../src/binding.js";
import { CAPABILITY_PREDICATES, PROVENANCE_PREDICATES } from "../src/foundations.js";

const f = (predicate: string, ...args: string[]) => ({ predicate, args });
const gate = {
  Request: { kind: "input" as const, args: ["Q", "Principal", "EventKind"], meaning: "Request." },
  Allow: { kind: "derived" as const, args: ["Q"], meaning: "Permission." },
  Deny: { kind: "derived" as const, args: ["Q", "Reason"], meaning: "Refusal." },
};
const intent = { actor: "member", action: "read", resource: "item" };

it("uses principal and resource groups without forcing grants on every application", () => {
  const binding: RuntimeBinding = {
    version: 1,
    id: "group-policy",
    context: "Synthetic group permissions.",
    mechanisms: ["capability"],
    predicates: { ...gate, ...CAPABILITY_PREDICATES },
    decision: { request: "Request", allow: "Allow", deny: "Deny" },
    tests: [],
  };
  const rules = 'Allow(Q) :- Request(Q, P, E), Parameter(Q, "resource", R), Can(P, R, E).';
  const inputs = [
    f("Capability", "reviewers", "collection", "read"),
    f("PrincipalGroup", "member", "team"),
    f("PrincipalGroup", "team", "reviewers"),
    f("ResourceGroup", "collection", "item"),
  ];
  const session = createPolicySession(binding, compileApplicationPolicy(binding, rules), inputs);
  expect(session.check(intent).allowed).toBe(true);
  expect(session.check({ ...intent, actor: "other" }).allowed).toBe(false);
  expect(session.query('?- Can("member", R, E).').rows).toContainEqual(["item", "read"]);
  const memberships = 'Allow(Q) :- Request(Q, P, E), PrincipalGroup(P, "team").';
  expect(
    createPolicySession(binding, compileApplicationPolicy(binding, memberships), [
      f("PrincipalGroup", "member", "team"),
    ]).check(intent).allowed,
  ).toBe(true);
});

it("tracks unlabelled data origins through a conservative diamond", () => {
  const binding: RuntimeBinding = {
    version: 1,
    id: "data-origins",
    context: "Versioned objects and declared dependencies.",
    mechanisms: ["provenance"],
    predicates: { ...gate, ...PROVENANCE_PREDICATES },
    decision: { request: "Request", allow: "Allow", deny: "Deny" },
    tests: [],
  };
  const rules =
    'Allow(Q) :- Request(Q, P, E).\nDeny(Q, "private_origin") :- Request(Q, P, E), Parameter(Q, "resource", D), Provenance(D, "private_owner").';
  const inputs = [
    f("Source", "public_owner", "a"),
    f("Source", "private_owner", "b"),
    f("DependsOn", "c", "a"),
    f("DependsOn", "c", "b"),
    f("DependsOn", "item", "c"),
  ];
  const session = createPolicySession(binding, compileApplicationPolicy(binding, rules), inputs);
  expect(session.query('?- Provenance("item", P).').rows.sort()).toEqual([
    ["private_owner"],
    ["public_owner"],
  ]);
  expect(session.check(intent).reasons).toEqual(["private_origin"]);
  expect(session.check({ ...intent, resource: "a" }).allowed).toBe(true);
  expect(() =>
    compileApplicationPolicy(binding, `${rules}\nProvenance(D, P) :- Source(P, D).`),
  ).toThrow("foundation");
});

it("does not accept source provenance from a request-parameter alias", () => {
  const binding = {
    version: 1,
    id: "bad-alias",
    context: "Sources remain backend-owned.",
    mechanisms: ["provenance"],
    predicates: { ...gate, ...PROVENANCE_PREDICATES },
    decision: { request: "Request", allow: "Allow", deny: "Deny", parameters: "Source" },
    tests: [],
  };
  expect(() => compileApplicationPolicy(binding, "Allow(Q) :- Request(Q, P, E).")).toThrow();
});
