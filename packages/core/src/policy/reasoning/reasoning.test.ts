import { describe, expect, it } from "vitest";
import { factKey } from "../datalog.js";
import {
  ACTIONS,
  applyAction,
  minimalPrevention,
  PREVENTABLE_PRESET,
  parsePreventable,
  speculative,
  terminalQuery,
  whatIf,
  why,
} from "./analysis.js";
import { contains, evaluate, f } from "./policy.js";
import { createEpisode, inputs, NovaRuntime } from "./runtime.js";

const q = "DenyReceive(auditor_a, mH)";
const findAction = (sender: string, receiver: string) =>
  ACTIONS.find((a) => a.sender === sender && a.receiver === receiver)!;

describe("executable Nova policy reasoning", () => {
  it("derives the base denial from runtime events and proves it back to source tags", () => {
    const r = createEpisode();
    expect(contains(r.closure().facts, f("DenyReceive", "auditor_a", "mH"))).toBe(true);
    const proof = JSON.stringify(why(inputs(r.state), q));
    for (const name of [
      "Incoming",
      "Carries",
      "Knows",
      "Received",
      "DependsOn",
      "TrustedCarry",
      "Before",
    ])
      expect(proof).toContain(name);
    expect(r.state.events).toHaveLength(11);
    expect(
      r.state.records.every(
        (record) => record.source === "config" || typeof record.event === "number",
      ),
    ).toBe(true);
  });
  it("what-if removes both records on a copy and retracts derived facts", () => {
    const r = createEpisode(),
      before = JSON.stringify(r.state);
    const result = whatIf(
      inputs(r.state),
      "Receiver(auditor_a, mF). Received(auditor_a, mF).",
      "",
      q,
    );
    expect(result.result).toBe(false);
    expect(result.removed).toContainEqual(f("Knows", "auditor_a", "nova", "facility"));
    expect(result.removed).toContainEqual(f("DenyReceive", "auditor_a", "mH"));
    expect(JSON.stringify(r.state)).toBe(before);
  });
  it("computes both minimum one-event alternatives and responds to changed event sets", () => {
    const r = createEpisode(),
      events = parsePreventable(PREVENTABLE_PRESET);
    const result = minimalPrevention(inputs(r.state), events, q);
    expect(result.size).toBe(1);
    expect(result.solutions).toEqual([["eP"], ["eF"]]);
    expect(minimalPrevention(inputs(r.state), [events[1]!], q).solutions).toEqual([["eF"]]);
    expect(minimalPrevention(inputs(r.state), [], q).solutions).toEqual([]);
  });
  it("Auditor B cannot receive HR; granting the actual config capability changes the answer", () => {
    const r = createEpisode("earlier"),
      action = findAction("hr", "auditor_b");
    const denied = applyAction(r.state, action);
    expect(denied.allowed).toBe(false);
    expect(JSON.stringify(denied.proof)).toContain("not HasCap(auditor_b, hr_review)");
    const changed = r.snapshot();
    changed.records.push({
      fact: f("HasCap", "auditor_b", "hr_review"),
      owner: "auditor_b",
      source: "config",
      lifetime: "local",
    });
    expect(applyAction(changed, action).allowed).toBe(true);
  });
  it("discovers Facility -> A as immediately legal but dead-ending", () => {
    const r = createEpisode("earlier"),
      before = JSON.stringify(r.state);
    const result = speculative(r.state, ACTIONS, "Finished(nova)");
    expect(result.edges.find((e) => e.action.id === "facility->auditor_a")?.classification).toBe(
      "dead-ending",
    );
    expect(
      result.edges
        .find((e) => e.action.id === "facility->auditor_a")
        ?.successor?.edges.every((e) => e.classification === "denied"),
    ).toBe(true);
    expect(JSON.stringify(r.state)).toBe(before);
  });
  it("discovers Facility -> B completion and actually replays the witness through the receive gate", () => {
    let r = createEpisode("earlier");
    const result = speculative(r.state, ACTIONS, "Finished(nova)");
    const edge = result.edges.find((e) => e.action.id === "facility->auditor_b")!;
    expect(edge.classification).toBe("completion-preserving");
    expect(edge.trace?.map((a) => a.id)).toEqual(["facility->auditor_b", "hr->auditor_a"]);
    for (const action of edge.trace!) {
      const next = applyAction(r.state, action);
      expect(next.allowed).toBe(true);
      r = next.runtime;
    }
    expect(contains(r.closure().facts, f("Finished", "nova"))).toBe(true);
  });
  it("derivations disappear when source support is removed; derived facts cannot be injected", () => {
    const input = inputs(createEpisode().state).filter((f) => f.predicate !== "TrustedCarry");
    const result = evaluate(input);
    for (const name of ["Carries", "Knows", "DenyReceive", "Audited", "Finished"])
      expect(result.facts.some((f) => f.predicate === name)).toBe(false);
    expect(() => evaluate([...input, f("Finished", "nova")])).toThrow(/read-only/);
    expect(() => whatIf(input, "", "Knows(auditor_a, nova, hiring).", q)).toThrow(/read-only/);
  });
  it("records Sender and Before from execution, and denies without delivering payload or knowledge", () => {
    const r = createEpisode();
    expect(inputs(r.state)).toContainEqual(f("Before", "m0", "mH"));
    const before = r.accessible("auditor_a");
    expect(r.settle("mH").allowed).toBe(false);
    expect(r.accessible("auditor_a")).toEqual(before);
    expect(inputs(r.state)).not.toContainEqual(f("Received", "auditor_a", "mH"));
    expect(inputs(r.state).some((f) => f.predicate === "Incoming")).toBe(false);
    expect(r.state.events.at(-1)?.check).toContainEqual(f("DenyReceive", "auditor_a", "mH"));
    expect(() => r.settle("mH")).toThrow(/pending/);
  });
  it("checks every pending receive against current state, so interleaved sends cannot bypass the limit", () => {
    const r = createEpisode("earlier");
    r.send("facility", "auditor_a", "xF", "Facility reply");
    r.send("hr", "auditor_a", "xH", "HR reply");
    expect(r.settle("xF").allowed).toBe(true);
    expect(r.settle("xH").allowed).toBe(false);
  });
  it("supports real variable joins, custom recursive query rules, and read-only protected predicates", () => {
    const r = createEpisode();
    expect(terminalQuery(r.state, "?- Knows(auditor_a, nova, Part).").rows).toEqual([
      ["procurement"],
      ["facility"],
    ]);
    expect(
      terminalQuery(
        r.state,
        "Reason(M, P) :- Incoming(A, M), Carries(M, nova, P). ?- Reason(M, P).",
      ).rows,
    ).toEqual([["mH", "hiring"]]);
    expect(
      terminalQuery(
        r.state,
        "Edge(a,b). Edge(b,c). Reach(X,Y) :- Edge(X,Y). Reach(X,Z) :- Reach(X,Y), Edge(Y,Z). ?- Reach(a,X).",
      ).rows,
    ).toEqual([["b"], ["c"]]);
    expect(() => terminalQuery(r.state, "Finished(nova). ?- Finished(nova).")).toThrow(/read-only/);
  });
  it("search respects the configured action universe and modified config", () => {
    const r = createEpisode("earlier");
    expect(
      speculative(
        r.state,
        [findAction("facility", "auditor_a"), findAction("hr", "auditor_a")],
        "Finished(nova)",
      ).trace,
    ).toBeNull();
    r.state.records.push({
      fact: f("HasCap", "auditor_b", "hr_review"),
      owner: "auditor_b",
      source: "config",
      lifetime: "local",
    });
    expect(
      speculative(r.state, ACTIONS, "Finished(nova)").edges.find(
        (e) => e.action.id === "facility->auditor_a",
      )?.classification,
    ).toBe("completion-preserving");
  });
  it("propagates transitive labels from every prior successful receive", () => {
    const r = createEpisode("earlier");
    r.send("auditor_a", "board", "report", "Procurement review");
    expect(r.closure().facts).toContainEqual(f("Carries", "report", "nova", "procurement"));
    expect(r.closure().facts).toContainEqual(f("DependsOn", "report", "mP"));
  });
  it("covers multi-label incoming messages and Board exemption with the same Datalog engine", () => {
    const input = [
      f("Incoming", "auditor_a", "bundle"),
      ...["procurement", "facility", "hiring"].map((p) => f("TrustedCarry", "bundle", "nova", p)),
      ...inputs(new NovaRuntime().state),
    ];
    expect(evaluate(input).facts).toContainEqual(f("DenyReceive", "auditor_a", "bundle"));
    const board = input
      .filter((f) => f.predicate !== "Incoming" && f.predicate !== "Requires")
      .concat(f("Incoming", "board", "bundle"));
    expect(evaluate(board).facts.some((f) => f.predicate === "DenyReceive")).toBe(false);
  });
  it("knows only allowed receives, and no derived fact is persisted as input", () => {
    const r = createEpisode();
    expect(
      r.state.records.some((r) =>
        ["Knows", "Carries", "DenyReceive", "Finished"].includes(r.fact.predicate),
      ),
    ).toBe(false);
    expect(r.state.records.map((r) => factKey(r.fact)).length).toBe(
      new Set(r.state.records.map((r) => factKey(r.fact))).size,
    );
  });
});
