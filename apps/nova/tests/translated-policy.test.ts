import { describe, expect, it } from "vitest";
import { terminalQuery, whatIf, why } from "../src/analysis.js";
import { novaDocuments } from "../src/documents.js";
import { NOVA_RULES } from "../src/policy.js";
import { closureConformance, comparePrevention } from "../src/prevention.js";
import { createEpisode, NovaRuntime } from "../src/runtime.js";
import { NovaService } from "../src/service.js";
import { ServiceProcess } from "../src/service-process.js";
import { createPolicyArtifact, readPolicyArtifact, ruleSource } from "../src/translated-policy.js";
import { NOVA_WORKER_PATH } from "../src/worker-path.js";

function fixture(
  source = ruleSource(NOVA_RULES.filter((rule) => rule.id.startsWith("three-tag"))),
) {
  return createPolicyArtifact(
    novaDocuments(),
    [
      { id: "P1", basis: "builtin", datalog: "", notes: "Lineage" },
      { id: "P2", basis: "builtin", datalog: "", notes: "Capability" },
      {
        id: "P3",
        basis: "extension",
        datalog: source,
        notes: "Offline test fixture, not model output",
      },
      { id: "P4", basis: "builtin", datalog: "", notes: "Delivery gate" },
      {
        id: "P5",
        basis: "extension",
        datalog: ruleSource(NOVA_RULES.filter((rule) => !rule.id.startsWith("three-tag"))),
        notes: "Offline audit fixture",
      },
    ],
    "offline test fixture",
  );
}
describe("Nova generated extensions and actual enforcement", () => {
  it("keeps the golden program/protocol and an independent parsed extension behaviorally aligned", () => {
    const results = comparePrevention(fixture());
    expect(results).toHaveLength(8);
    expect(
      results.every((test) => test.matches && test.golden.passed && test.translated?.passed),
    ).toBe(true);
    const denied = results
      .find((test) => test.name === "Third distinct tag")!
      .translated!.observations.at(-1)!;
    expect(denied).toMatchObject({
      allowed: false,
      denyDerived: true,
      received: false,
      bodyVisible: false,
    });
  });
  it("finds a removed exposure gate without substituting golden rules, and refuses activation", () => {
    const policy = fixture(ruleSource(NOVA_RULES.filter((r) => !r.id.startsWith("three-tag"))));
    const results = comparePrevention(policy);
    expect(
      results.find((test) => test.name === "Third distinct tag")!.translated!.observations.at(-1)!
        .allowed,
    ).toBe(true);
    const service = new NovaService();
    const before = service.runtime.snapshot();
    expect(() => service.run({ operation: "start-policy", revision: 1, artifact: policy })).toThrow(
      /failed the prevention/,
    );
    expect(service.runtime.snapshot()).toEqual(before);
  });
  it("keeps the policy identity in historical views, query, proof, reset and checkpoint restore", () => {
    const policy = fixture();
    const service = new NovaService();
    service.runtime = createEpisode("denial", policy);
    expect(
      terminalQuery(service.runtime.state, "?- DenyReceive(auditor_a, mH).", "auditor_a").rows,
    ).toHaveLength(1);
    expect(why(service.runtime.state, "DenyReceive(auditor_a, mH)", "auditor_a")).not.toBeNull();
    service.run({ operation: "settle", id: "mH", revision: 1 });
    const event = service.runtime.state.events.at(-1)!;
    expect(service.selected({ event: event.seq, side: "before" }).policy?.id).toBe(policy.id);
    expect(
      new NovaRuntime(JSON.parse(JSON.stringify(service.runtime.snapshot()))).state.policy?.id,
    ).toBe(policy.id);
    expect(service.runtime.accessible("auditor_a").some((m) => m.id === "mH")).toBe(false);
    expect(
      service.run({ operation: "conformance", revision: 2, event: event.seq, side: "before" }),
    ).toMatchObject({ gates: [{ message: "mH", localDeny: true, fullCopyDeny: true }] });
    expect(service.run({ operation: "conformance", revision: 2 })).toMatchObject({ gates: [] });
    service.run({ operation: "reset", preset: "initial", revision: 2 });
    expect(service.runtime.state.policy?.id).toBe(policy.id);
    service.run({ operation: "start-policy", revision: 3 });
    expect(service.runtime.state.policy).toBeUndefined();
  });
  it("uses a differing generated policy in Why and What-if, never the golden fallback", () => {
    const runtime = createEpisode("initial", fixture("DenyReceive(P, M) :- Incoming(P, M)."));
    runtime.send("hr", "auditor_a", "plain", "ordinary message");
    expect(why(runtime.state, "DenyReceive(auditor_a, plain)", "auditor_a")).not.toBeNull();
    expect(whatIf(runtime.state, "", "", "DenyReceive(auditor_a, plain)").result).toBe(true);
    expect(runtime.settle("plain").allowed).toBe(false);
    expect(runtime.accessible("auditor_a")).toEqual([]);
  });
  it("checks the closure union and decision location and detects missing transport", () => {
    const runtime = createEpisode("denial", fixture());
    expect(closureConformance(runtime.state).equivalent).toBe(true);
    runtime.state.stores.auditor_a = runtime.state.stores.auditor_a!.filter(
      (r) => !(r.fact.predicate === "TransportTag" && r.fact.args[0] === "mH"),
    );
    const result = closureConformance(runtime.state);
    expect(result.equivalent).toBe(false);
    expect(result.gates).toContainEqual({
      principal: "auditor_a",
      message: "mH",
      localDeny: false,
      fullCopyDeny: true,
    });
    expect(() => runtime.settle("mH")).toThrow(/Incomplete tag envelope/);
  });
  it("rejects changed foundation/protocol/identity, unsafe rules and input writes", () => {
    expect(() => readPolicyArtifact({ ...fixture(), foundation: "other" })).toThrow(/foundation/);
    expect(() => readPolicyArtifact({ ...fixture(), id: "other" })).toThrow(/identity/);
    expect(() =>
      readPolicyArtifact({ ...fixture(), protocol: { ...fixture().protocol, replicated: [] } }),
    ).toThrow(/protocol/);
    expect(() => fixture("HasCap(P, C) :- Requires(T, C), Auditor(P).")).toThrow(/cannot write/);
    expect(() => fixture("DenyReceive(P, M) :- not HasCap(P, C).")).toThrow();
    expect(() => fixture("Finished(G) :- not Finished(G), AuditGoal(G, A, B, C).")).toThrow();
    expect(() => fixture('Finished("nova").')).toThrow(/ground facts/);
  });
  it("restores translated policy after worker restart without falling back to golden", async () => {
    const worker = new ServiceProcess(NOVA_WORKER_PATH);
    try {
      const state = (await worker.run({
        operation: "start-policy",
        revision: 1,
        artifact: fixture(),
      })) as { policyIdentity: { id: string }; version: number };
      worker.close();
      const restored = (await worker.run({ operation: "state" })) as typeof state;
      expect(restored.policyIdentity).toEqual(state.policyIdentity);
      expect(restored.version).toBe(state.version);
    } finally {
      worker.close();
    }
  });
});
