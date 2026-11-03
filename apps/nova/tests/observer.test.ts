import { describe, expect, it } from "vitest";
import { terminalQuery, whatIf } from "../src/analysis.js";
import { novaDocuments } from "../src/documents.js";
import { f, NOVA_RULES, parseInputs } from "../src/policy.js";
import { PROTOCOL } from "../src/protocol.js";
import { createEpisode, NovaRuntime } from "../src/runtime.js";
import { allRecords } from "../src/store-records.js";
import {
  compileExtensions,
  createPolicyArtifact,
  readPolicyArtifact,
  ruleSource,
} from "../src/translated-policy.js";
import { savedTranslationReview } from "../src/translation-review.js";

describe("observer-only completion", () => {
  it("rejects local rules depending on global completion, including negative dependencies", () => {
    for (const body of ["Finished(G)", "AuditGoal(G, A, B, C), not Finished(G)"])
      expect(() =>
        compileExtensions([
          {
            id: "P1",
            basis: "extension",
            notes: "test",
            datalog: `DenyReceive(P, M) :- Incoming(P, M), ${body}.`,
          },
        ]),
      ).toThrow(/Observer-only/);
    expect(() => parseInputs("Covered(nova_hiring).")).toThrow(/read-only/);
    expect(() => parseInputs("AuditReceipt(auditor_a, nova_hiring).")).toThrow(/Unknown/);
    expect(PROTOCOL.transfers).not.toHaveProperty("audit");
  });

  it("uses generated completion rules only in the global observer and never in local denial", () => {
    const policy = createPolicyArtifact(
      novaDocuments(),
      [
        { id: "P1", basis: "builtin", notes: "test", datalog: "" },
        { id: "P2", basis: "builtin", notes: "test", datalog: "" },
        {
          id: "P3",
          basis: "extension",
          notes: "test",
          datalog: ruleSource(NOVA_RULES.filter((r) => r.id.startsWith("three-tag"))),
        },
        { id: "P4", basis: "builtin", notes: "test", datalog: "" },
        {
          id: "P5",
          basis: "extension",
          notes: "deliberately different test goal",
          datalog: "Finished(G) :- AuditGoal(G, T1, T2, T3).",
        },
      ],
      "offline fixture",
    );
    const runtime = createEpisode("denial", policy);
    const before = runtime.snapshot();
    expect(terminalQuery(runtime.state, "?- Finished(nova).", "debug").rows).toHaveLength(1);
    for (const owner of Object.keys(runtime.state.stores))
      expect(runtime.closure(owner).facts.some((f) => f.predicate === "Finished")).toBe(false);
    expect(runtime.snapshot()).toEqual(before);
    expect(runtime.settle("mH").allowed).toBe(false);
  });

  it("combines split audit coverage without persisting summaries", () => {
    const runtime = createEpisode("earlier");
    runtime.send("facility", "auditor_b", "f", "facility");
    runtime.settle("f");
    runtime.send("hr", "auditor_a", "h", "hiring");
    runtime.settle("h");
    expect(terminalQuery(runtime.state, "?- Finished(nova).", "debug").rows).toHaveLength(1);
    const before = runtime.snapshot();
    expect(whatIf(runtime.state, "Received(auditor_a, h).", "", "Finished(nova)").result).toBe(
      false,
    );
    expect(runtime.snapshot()).toEqual(before);
    expect(
      allRecords(runtime.state).some((r) =>
        ["AuditReceipt", "Covered", "Finished"].includes(r.fact.predicate),
      ),
    ).toBe(false);
    expect(runtime.accessible("auditor_a")).toEqual(
      new NovaRuntime(before).accessible("auditor_a"),
    );
  });

  it("upgrades old golden snapshots without retaining audit receipts or changing messages", () => {
    const old = createEpisode().snapshot();
    old.protocolVersion = 1;
    const receipt = {
      fact: f("AuditReceipt", "auditor_a", "nova_procurement"),
      owner: "board",
      source: "protocol" as const,
      lifetime: "local" as const,
    };
    old.stores.board!.push(receipt);
    old.events[0]!.after.board!.push(structuredClone(receipt));
    old.events[0]!.added.push(receipt.fact);
    const before = structuredClone(old);
    const restored = new NovaRuntime(old);
    expect(old).toEqual(before);
    expect(restored.state.protocolVersion).toBe(3);
    expect(restored.state.messages).toEqual(old.messages);
    expect(restored.state.revision).toBe(old.revision);
    expect(JSON.stringify(restored.snapshot())).not.toContain("AuditReceipt");
    expect(new NovaRuntime(restored.snapshot()).snapshot()).toEqual(restored.snapshot());
    expect(restored.settle("mH").allowed).toBe(false);
  });

  it("keeps the old model output historical and refuses installation or translated checkpoint upgrade", () => {
    const review = savedTranslationReview();
    expect(review.historical).toBe(true);
    expect(review.eligible).toBe(false);
    expect(() => readPolicyArtifact(review.artifact)).toThrow(/foundation\/protocol/);
    expect(
      () => new NovaRuntime({ ...createEpisode().snapshot(), policy: review.artifact }),
    ).toThrow(/foundation\/protocol/);
  });
});
