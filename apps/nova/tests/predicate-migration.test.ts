import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { describe, expect, it } from "vitest";
import { terminalQuery, why } from "../src/analysis.js";
import { legacyCheckpoint } from "../src/legacy-checkpoint.fixture.js";
import { createEpisode, NovaRuntime } from "../src/runtime.js";
import { allRecords } from "../src/store-records.js";

const oldNames: Record<string, string> = {
  MessageTag: "Propagated",
  HasReceivedTag: "Knows",
  Covered: "Audited",
  ReceivedBeforeSend: "Before",
  MayDependOn: "DependsOn",
};
function oldSnapshot() {
  const state = createEpisode().snapshot();
  state.protocolVersion = 2;
  const visit = (value: unknown): void => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    const object = value as Record<string, unknown>;
    if (typeof object.predicate === "string" && Array.isArray(object.args)) {
      const fact = object as PolicyFact;
      fact.predicate = oldNames[fact.predicate] ?? fact.predicate;
    } else Object.values(object).forEach(visit);
  };
  visit(state);
  for (const stores of [state.stores, ...state.events.flatMap((e) => [e.before, e.after])])
    for (const rows of Object.values(stores))
      for (const row of [...rows])
        if (row.fact.predicate === "Received")
          rows.push({ ...structuredClone(row), fact: { ...row.fact, predicate: "Receiver" } });
  return state;
}

describe("Nova predicate vocabulary migration", () => {
  it("migrates envelopes and event snapshots and preserves local decisions in both checkpoint layouts", () => {
    const old = oldSnapshot();
    const before = structuredClone(old);
    for (const input of [old, legacyCheckpoint(old)]) {
      const runtime = new NovaRuntime(input);
      expect(runtime.state.protocolVersion).toBe(3);
      expect(runtime.state.revision).toBe(old.revision);
      expect(runtime.state.messages.map(({ labels: _, ...m }) => m)).toEqual(
        old.messages.map(({ labels: _, ...m }) => m),
      );
      expect(JSON.stringify(runtime.snapshot())).not.toMatch(
        /"(?:Propagated|Knows|Audited|Before|DependsOn|Receiver)"/,
      );
      expect(
        terminalQuery(runtime.state, "?- HasReceivedTag(auditor_a, Tag).", "auditor_a").rows,
      ).toHaveLength(2);
      expect(why(runtime.state, "Deny(mH, message_policy)", "auditor_a")).not.toBeNull();
      expect(new NovaRuntime(runtime.snapshot()).snapshot()).toEqual(runtime.snapshot());
      expect(runtime.settle("mH").allowed).toBe(false);
    }
    expect(old).toEqual(before);
  });
  it("does not invent successful reception from an orphan old Receiver alias", () => {
    const old = oldSnapshot();
    old.stores.auditor_a = old.stores.auditor_a!.filter((r) => r.fact.predicate !== "Received");
    const runtime = new NovaRuntime(old);
    expect(allRecords(runtime.state).some((r) => r.fact.predicate === "Receiver")).toBe(false);
    expect(
      terminalQuery(runtime.state, "?- HasReceivedTag(auditor_a, Tag).", "auditor_a").rows,
    ).toEqual([]);
  });
});
