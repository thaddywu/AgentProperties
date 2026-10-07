import { describe, expect, it } from "vitest";
import { evaluateLifecycle } from "./lifecycle.js";
import { createEpisode } from "./runtime.js";

const f = (predicate: string, ...args: string[]) => ({ predicate, args });
const inputs = () => [
  f("ResourceType", "server_a", "server"),
  f("ResourceState", "server_a", "free"),
  f("ResourceType", "server_b", "server"),
  f("ResourceState", "server_b", "occupied"),
  f("Transition", "server", "reserve", "free", "occupied"),
  f("Transition", "server", "release", "occupied", "free"),
];
describe("independent lifecycle foundation", () => {
  it("derives state-indexed actions independently of current state and resource type", () => {
    const facts = evaluateLifecycle([
      ...inputs(),
      f("ResourceType", "document", "document"),
      f("ResourceState", "document", "free"),
    ]).facts;
    for (const resource of ["server_a", "server_b"]) {
      expect(facts).toContainEqual(f("EnabledAction", resource, "free", "reserve"));
      expect(facts).toContainEqual(f("EnabledAction", resource, "occupied", "release"));
      expect(facts).not.toContainEqual(f("EnabledAction", resource, "occupied", "reserve"));
    }
    expect(
      facts.some(
        (fact) =>
          ["EnabledAction", "ReachableState"].includes(fact.predicate) &&
          fact.args[0] === "document",
      ),
    ).toBe(false);
  });
  it("derives direct and transitive reachability without inventing zero-step paths", () => {
    const facts = evaluateLifecycle([
      ...inputs().filter(
        (fact) => !(fact.predicate === "Transition" && fact.args[1] === "release"),
      ),
      f("Transition", "server", "retire", "occupied", "retired"),
    ]).facts;
    expect(facts).toContainEqual(f("ReachableState", "server_a", "free", "occupied"));
    expect(facts).toContainEqual(f("ReachableState", "server_a", "free", "retired"));
    expect(facts).toContainEqual(f("ReachableState", "server_b", "free", "retired"));
    expect(facts).not.toContainEqual(f("ReachableState", "server_a", "retired", "free"));
    expect(facts).not.toContainEqual(f("ReachableState", "server_a", "free", "free"));
    expect(facts).not.toContainEqual(f("ReachableState", "server_a", "retired", "retired"));
    expect(facts).not.toContainEqual(f("ReachableState", "server_a", "free", "missing"));
  });
  it("terminates on cycles and derives self-reachability only through transitions", () => {
    const facts = evaluateLifecycle(inputs()).facts;
    expect(facts).toContainEqual(f("ReachableState", "server_a", "free", "free"));
    expect(facts).toContainEqual(f("ReachableState", "server_a", "occupied", "occupied"));
    expect(facts.filter((fact) => fact.predicate === "ReachableState")).toHaveLength(8);
  });
  it("changes current actions while preserving FSM relations, history, and old snapshots", () => {
    const before = inputs(),
      copy = structuredClone(before);
    const after = before.filter(
      (fact) => !(fact.predicate === "ResourceState" && fact.args[0] === "server_a"),
    );
    const event = f("ActionTaken", "e1", "server_a", "reserve", "free", "occupied");
    after.push(f("ResourceState", "server_a", "occupied"), event);
    const oldFacts = evaluateLifecycle(before).facts;
    const newFacts = evaluateLifecycle(after).facts;
    const currentActions = (facts: typeof oldFacts) =>
      facts
        .filter(
          (action) =>
            action.predicate === "EnabledAction" &&
            action.args[0] === "server_a" &&
            facts.some(
              (state) =>
                state.predicate === "ResourceState" &&
                state.args[0] === action.args[0] &&
                state.args[1] === action.args[1],
            ),
        )
        .map((action) => action.args[2]);
    expect(currentActions(oldFacts)).toEqual(["reserve"]);
    expect(currentActions(newFacts)).toEqual(["release"]);
    for (const fact of oldFacts.filter((fact) =>
      ["EnabledAction", "ReachableState"].includes(fact.predicate),
    ))
      expect(newFacts).toContainEqual(fact);
    expect(newFacts).toContainEqual(event);
    expect(before).toEqual(copy);
  });
  it("rejects conflicting states, ambiguous transitions, and injected derived facts", () => {
    expect(() =>
      evaluateLifecycle([...inputs(), f("ResourceState", "server_a", "occupied")]),
    ).toThrow(/Conflicting/);
    expect(() =>
      evaluateLifecycle([...inputs(), f("Transition", "server", "reserve", "free", "deleted")]),
    ).toThrow(/Ambiguous/);
    expect(() =>
      evaluateLifecycle([...inputs(), f("EnabledAction", "server_a", "free", "delete")]),
    ).toThrow(/Invalid/);
    expect(() =>
      evaluateLifecycle([...inputs(), f("BlockedAction", "server_a", "reserve")]),
    ).toThrow(/Invalid/);
    expect(() => evaluateLifecycle([f("ResourceState", "server_a", "free")])).toThrow(/type/);
  });
  it("does not create resources in Nova", () => {
    const runtime = createEpisode("initial");
    expect(
      Object.values(runtime.state.stores)
        .flat()
        .some((r) => r.fact.predicate === "ResourceState"),
    ).toBe(false);
  });
});
