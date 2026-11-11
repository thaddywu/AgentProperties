import { evaluateLifecycle, LIFECYCLE_RULE_TEXT } from "@rakazo/policy-runtime/lifecycle";
import { expect, it } from "vitest";

const f = (predicate: string, ...args: string[]) => ({ predicate, args });
const inputs = () => [
  f("ResourceType", "a", "server"),
  f("ResourceState", "a", "idle"),
  f("AllowedTransition", "server", "reserve", "idle", "reserved"),
  f("AllowedTransition", "server", "start", "reserved", "running"),
];

it("shares reachability by type and matches only current transitions", () => {
  const facts = evaluateLifecycle(inputs()).facts;
  expect(facts).toContainEqual(f("ReachableState", "server", "idle", "running"));
  expect(facts).toContainEqual(f("CanTransition", "a", "reserve", "idle", "reserved"));
  expect(facts).not.toContainEqual(f("CanTransition", "a", "start", "reserved", "running"));
  expect(facts).not.toContainEqual(f("ReachableState", "server", "idle", "idle"));
});
it("handles cycles without inventing zero-step reachability", () => {
  const facts = evaluateLifecycle([
    ...inputs(),
    f("AllowedTransition", "server", "reset", "running", "idle"),
  ]).facts;
  expect(facts).toContainEqual(f("ReachableState", "server", "idle", "idle"));
});
it("updates current-state answers while leaving an earlier evaluation unchanged", () => {
  const before = evaluateLifecycle(inputs()).facts;
  const changed = inputs().map((fact) =>
    fact.predicate === "ResourceState" ? f("ResourceState", "a", "reserved") : fact,
  );
  const after = evaluateLifecycle(changed).facts;
  expect(after).toContainEqual(f("CanTransition", "a", "start", "reserved", "running"));
  expect(after).not.toContainEqual(f("CanTransition", "a", "reserve", "idle", "reserved"));
  expect(before).toContainEqual(f("CanTransition", "a", "reserve", "idle", "reserved"));
});
it("rejects conflicting state, ambiguous edges and derived input injection", () => {
  expect(() => evaluateLifecycle([...inputs(), f("ResourceState", "a", "running")])).toThrow(
    "Conflicting",
  );
  expect(() =>
    evaluateLifecycle([
      ...inputs(),
      f("AllowedTransition", "server", "reserve", "idle", "running"),
    ]),
  ).toThrow("Ambiguous");
  expect(() =>
    evaluateLifecycle([...inputs(), f("CanTransition", "a", "reserve", "idle", "reserved")]),
  ).toThrow("Invalid");
  expect(LIFECYCLE_RULE_TEXT).not.toContain("EnabledAction");
});
