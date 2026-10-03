import type { PolicyFact } from "@rakazo/contracts";
import { describe, expect, it } from "vitest";
import { factKey } from "../datalog.js";
import { terminalQuery, why } from "./analysis.js";
import { CONFIG } from "./config.js";
import { reconstructDebugView } from "./local-store.js";
import { DERIVED, evaluate, f } from "./policy.js";
import { createEpisode, inputs, NovaRuntime } from "./runtime.js";
import { PRINCIPALS } from "./shared.js";
import { allRecords, filterRecords } from "./store-records.js";

// A centralized oracle exists ONLY in this diagnostic test. The runtime never
// runs policy on the reconstructed union. Compare all derived predicates, not just denial.
const derivedKeys = (facts: PolicyFact[]) =>
  [...new Set(facts.filter((f) => DERIVED.has(f.predicate)).map(factKey))].sort();
function compare(runtime: NovaRuntime) {
  const state = runtime.snapshot();
  const distributed = derivedKeys(reconstructDebugView(state).facts);
  const reference = derivedKeys(evaluate(inputs(state)).facts);
  expect(distributed).toEqual(reference);
  expect(runtime.snapshot()).toEqual(state);
  return { distributed, reference };
}
const departments = ["procurement", "facility", "hr"];
const tag = (department: string) => `nova_${department === "hr" ? "hiring" : department}`;
const orders = departments.flatMap((a) =>
  departments
    .filter((b) => b !== a)
    .map((b) => [a, b, departments.find((c) => c !== a && c !== b)!]),
);
const cases = [false, true].flatMap((grantB) =>
  orders.flatMap((order) => Array.from({ length: 8 }, (_, mask) => ({ grantB, order, mask }))),
);

describe("distributed policy completeness against a diagnostic oracle", () => {
  for (const { grantB, order, mask } of cases) {
    it(`${order.join("/")} routing=${mask} B-capability=${grantB}`, () => {
      const runtime = new NovaRuntime();
      if (grantB) runtime.configure([...CONFIG, f("HasCap", "auditor_b", "hr_review")]);
      compare(runtime);
      for (const [i, department] of departments.entries()) {
        runtime.send("board", department, `source${i}`, "assignment", { tag: tag(department) });
        compare(runtime);
        expect(runtime.settle(`source${i}`).allowed).toBe(true);
        compare(runtime);
      }
      for (const [i, department] of order.entries()) {
        const receiver = mask & (1 << i) ? "auditor_b" : "auditor_a";
        runtime.send(department, receiver, `reply${i}`, "review");
        const reference = evaluate(inputs(runtime.state)).facts;
        compare(runtime);
        const expectedAllow = !reference.some(
          (fact) => factKey(fact) === factKey(f("DenyReceive", receiver, `reply${i}`)),
        );
        expect(runtime.settle(`reply${i}`).allowed).toBe(expectedAllow);
        compare(runtime);
      }
    });
  }
  it("compares interleaved pending messages and recursive multi-tag forwarding", () => {
    const runtime = createEpisode("earlier");
    runtime.send("facility", "auditor_a", "f1", "facility");
    compare(runtime);
    runtime.send("hr", "auditor_a", "h1", "hiring");
    compare(runtime);
    expect(runtime.settle("f1").allowed).toBe(true);
    compare(runtime);
    expect(runtime.settle("h1").allowed).toBe(false);
    compare(runtime);
    runtime.send("auditor_a", "auditor_b", "bundle", "two-tag report");
    compare(runtime);
    expect(runtime.settle("bundle").allowed).toBe(true);
    compare(runtime);
    runtime.send("auditor_b", "board", "relay", "forwarded report");
    compare(runtime);
    expect(runtime.settle("relay").allowed).toBe(true);
    compare(runtime);
  });
  it("publishes summaries when config enables auditing of previously received assignments", () => {
    const runtime = new NovaRuntime();
    for (const [i, department] of departments.entries())
      runtime.assign(`s${i}`, department, tag(department), "assignment");
    runtime.configure([...CONFIG, ...departments.map((p) => f("Auditor", p))]);
    expect(runtime.closure("board").facts).toContainEqual(f("Finished", "nova"));
    compare(runtime);
  });
  it("detects an omitted transport fact and fails closed instead of allowing delivery", () => {
    const runtime = createEpisode();
    filterRecords(
      runtime.state,
      (r) =>
        !(
          r.owner === "auditor_a" &&
          r.fact.predicate === "TransportTag" &&
          r.fact.args[0] === "mH"
        ),
    );
    const distributed = derivedKeys(reconstructDebugView(runtime.state).facts);
    const reference = derivedKeys(evaluate(inputs(runtime.state)).facts);
    expect(reference).toContain(factKey(f("DenyReceive", "auditor_a", "mH")));
    expect(distributed).not.toContain(factKey(f("DenyReceive", "auditor_a", "mH")));
    const before = runtime.snapshot();
    expect(() => runtime.settle("mH")).toThrow(/Incomplete tag envelope/);
    expect(runtime.snapshot()).toEqual(before);
  });
  it("rejects a pending message whose local receive intent is missing", () => {
    const runtime = createEpisode();
    filterRecords(runtime.state, (r) => r.fact.predicate !== "Incoming");
    const before = runtime.snapshot();
    expect(() => runtime.settle("mH")).toThrow(/Missing local receive intent/);
    expect(runtime.snapshot()).toEqual(before);
  });
  it("detects a missing audit receipt without repairing it by a hidden global join", () => {
    const runtime = new NovaRuntime();
    for (const [i, department] of departments.entries())
      runtime.assign(`s${i}`, department, tag(department), "assignment");
    for (const [i, department] of departments.entries()) {
      runtime.send(
        department,
        department === "facility" ? "auditor_b" : "auditor_a",
        `r${i}`,
        "audit",
      );
      runtime.settle(`r${i}`);
    }
    filterRecords(
      runtime.state,
      (r) =>
        !(
          r.owner === "board" &&
          r.fact.predicate === "AuditReceipt" &&
          r.fact.args[1] === "nova_hiring"
        ),
    );
    expect(runtime.closure("board").facts).not.toContainEqual(f("Finished", "nova"));
    expect(evaluate(inputs(runtime.state)).facts).toContainEqual(f("Finished", "nova"));
    const result = terminalQuery(runtime.state, "?- Finished(nova).", "debug");
    expect(result.rows).toEqual([]); // Debug reconstruction must not rerun policy on its union.
  });
  it("persists only local partitions and independent replicated configuration copies", () => {
    const runtime = createEpisode();
    const checkpoint = JSON.parse(JSON.stringify(runtime.snapshot()));
    expect(checkpoint).not.toHaveProperty("records");
    expect(Object.keys(checkpoint.stores).sort()).toEqual([...PRINCIPALS].sort());
    for (const [owner, records] of Object.entries(runtime.state.stores)) {
      expect(records.every((r) => r.owner === owner && r.lifetime !== "global")).toBe(true);
      expect(records.some((r) => r.fact.predicate === "TagGroup" && r.replicated)).toBe(true);
    }
    const a = runtime.state.stores.auditor_a!.find((r) => r.fact.predicate === "TagGroup")!;
    const b = runtime.state.stores.auditor_b!.find((r) => factKey(r.fact) === factKey(a.fact))!;
    expect(a).not.toBe(b);
    expect(a.fact).not.toBe(b.fact);
    expect(
      runtime.state.events.every((e) => !Array.isArray(e.before) && !Array.isArray(e.after)),
    ).toBe(true);
    expect(new NovaRuntime(checkpoint).snapshot()).toEqual(runtime.snapshot());
  });
  it("answers a local query and proof without even accessing another store", () => {
    const runtime = createEpisode();
    Object.defineProperty(runtime.state.stores, "auditor_b", {
      enumerable: true,
      get() {
        throw new Error("Remote store accessed");
      },
    });
    expect(
      terminalQuery(runtime.state, "?- Knows(auditor_a, Tag).", "auditor_a").rows,
    ).toHaveLength(2);
    expect(why(runtime.state, "DenyReceive(auditor_a, mH)", "auditor_a")).not.toBeNull();
    expect(() => terminalQuery(runtime.state, "?- Auditor(A).", "debug")).toThrow(
      /Remote store accessed/,
    );
  });
  it("reconstructs each debug query afresh and leaves local stores unchanged", () => {
    const runtime = createEpisode();
    const before = runtime.snapshot();
    expect(terminalQuery(runtime.state, "?- Knows(A, Tag).", "auditor_b").rows).toEqual([]);
    expect(terminalQuery(runtime.state, "?- Knows(auditor_a, Tag).", "debug").rows).toHaveLength(2);
    expect(runtime.snapshot()).toEqual(before);
    filterRecords(
      runtime.state,
      (r) =>
        !(r.owner === "auditor_a" && r.fact.predicate === "Received" && r.fact.args[1] === "mF"),
    );
    expect(terminalQuery(runtime.state, "?- Knows(auditor_a, Tag).", "debug").rows).toEqual([
      ["nova_procurement"],
    ]);
    expect(runtime.state).not.toHaveProperty("facts");
    expect(allRecords(runtime.state).every((r) => r.owner !== "global")).toBe(true);
  });
});
