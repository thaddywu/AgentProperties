import { describe, expect, it } from "vitest";
import { ACTIONS, applyAction, speculative, terminalQuery } from "./analysis.js";
import { legacyCheckpoint } from "./legacy-checkpoint.fixture.js";
import { localClosure, localInputs } from "./local-store.js";
import { contains, f } from "./policy.js";
import { PROTOCOL } from "./protocol.js";
import { createEpisode, NovaRuntime, view } from "./runtime.js";
import { allRecords, filterRecords } from "./store-records.js";

const finish = () => {
  let runtime = createEpisode("earlier");
  for (const id of ["facility->auditor_b", "hr->auditor_a"])
    runtime = applyAction(runtime.state, ACTIONS.find((a) => a.id === id)!).runtime;
  return runtime;
};
describe("protocol-defined local stores", () => {
  it("does not expose another principal's history, capabilities or source tags", () => {
    const runtime = createEpisode();
    const local = localInputs(runtime.state, "auditor_a");
    expect(local.some((f) => ["Sender", "Before", "TrustedSource"].includes(f.predicate))).toBe(
      false,
    );
    expect(local).toContainEqual(f("TransportTag", "mH", "nova_hiring"));
    expect(runtime.closure("auditor_b").facts.some((f) => f.predicate === "Knows")).toBe(false);
    expect(terminalQuery(runtime.state, "?- HasCap(A, C).", "auditor_b").rows).toEqual([]);
    expect(terminalQuery(runtime.state, "?- Knows(A, Tag).", "auditor_b").rows).toEqual([]);
  });
  it("cannot silently obtain a missing envelope from another store's Propagated", () => {
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
    expect(runtime.closure("hr").facts).toContainEqual(f("Propagated", "mH", "nova_hiring"));
    expect(runtime.closure("auditor_a").facts).not.toContainEqual(
      f("Propagated", "mH", "nova_hiring"),
    );
    expect(runtime.closure("auditor_a").facts).not.toContainEqual(
      f("DenyReceive", "auditor_a", "mH"),
    );
  });
  it("uses protocol patterns to bind local derivation before evaluation", () => {
    const runtime = createEpisode();
    const pattern = PROTOCOL.local.Knows!;
    try {
      PROTOCOL.local.Knows = ["auditor_b", "_"];
      expect(
        localClosure(runtime.state, "auditor_a").facts.some((f) => f.predicate === "Knows"),
      ).toBe(false);
    } finally {
      PROTOCOL.local.Knows = pattern;
    }
  });
  it("keeps pending labels temporary and discards them on denial without learning the payload", () => {
    const runtime = createEpisode();
    expect(
      allRecords(runtime.state).find(
        (r) =>
          r.owner === "auditor_a" && r.fact.predicate === "TransportTag" && r.fact.args[0] === "mH",
      )?.lifetime,
    ).toBe("temporary");
    expect(runtime.settle("mH").allowed).toBe(false);
    expect(runtime.closure("auditor_a").facts).not.toContainEqual(
      f("TransportTag", "mH", "nova_hiring"),
    );
    expect(runtime.closure("auditor_a").facts).not.toContainEqual(
      f("Knows", "auditor_a", "nova_hiring"),
    );
  });
  it("requires audit receipts at Board for Finished, without transferring auditors' Knows", () => {
    const runtime = finish();
    expect(view(runtime.state).finished).toBe(true);
    expect(runtime.closure("auditor_a").facts).not.toContainEqual(f("Finished", "nova"));
    expect(localInputs(runtime.state, "board").some((f) => f.predicate === "Received")).toBe(false);
    expect(runtime.closure("board").facts.some((f) => f.predicate === "Knows")).toBe(false);
    filterRecords(
      runtime.state,
      (r) =>
        !(
          r.owner === "board" &&
          r.fact.predicate === "AuditReceipt" &&
          r.fact.args[1] === "nova_hiring"
        ),
    );
    expect(runtime.closure("auditor_a").facts).toContainEqual(f("Audited", "nova_hiring"));
    expect(view(runtime.state).finished).toBe(false);
  });
  it("retains received label copies even if the original source is removed later", () => {
    const runtime = createEpisode();
    filterRecords(runtime.state, (r) => r.fact.predicate !== "TrustedSource");
    expect(runtime.closure("auditor_a").facts).toContainEqual(
      f("Knows", "auditor_a", "nova_facility"),
    );
    expect(runtime.closure("board").facts).not.toContainEqual(
      f("Propagated", "mF0", "nova_facility"),
    );
  });
  it("upgrades old checkpoint envelopes and histories without resetting messages or revision", () => {
    const old = legacyCheckpoint(createEpisode().snapshot());
    delete old.protocolVersion;
    old.records = old.records.filter((r) => r.source !== "protocol");
    for (const event of old.events) {
      event.before = event.before.filter((r) => r.source !== "protocol");
      event.after = event.after.filter((r) => r.source !== "protocol");
    }
    const runtime = new NovaRuntime(old);
    expect(runtime.state.revision).toBe(old.revision);
    expect(runtime.state.messages).toEqual(old.messages);
    expect(contains(runtime.closure("auditor_a").facts, f("DenyReceive", "auditor_a", "mH"))).toBe(
      true,
    );
    expect(new NovaRuntime(runtime.snapshot()).state.stores).toEqual(runtime.state.stores);
  });
  it("finds the completion through independent local gates and actual summary transfers", () => {
    const runtime = createEpisode("earlier");
    const result = speculative(runtime.state, ACTIONS, "Finished(nova)");
    expect(result.trace?.map((a) => a.id)).toEqual(["facility->auditor_b", "hr->auditor_a"]);
  });
});
