import { describe, expect, it } from "vitest";
import type { Rule } from "../datalog.js";
import { terminalQuery } from "./analysis.js";
import { f } from "./policy.js";
import { NovaRuntime } from "./runtime.js";
import { explainSouffle, runSouffle } from "./souffle.js";

describe("native Soufflé boundary", () => {
  it("round-trips quoted symbols, commas and newlines through native output", () => {
    const value = 'a,"b"\nsecond line';
    const rule: Rule = {
      id: "copy",
      head: f("Copy", "X"),
      body: [f("Source", "X")],
      distinct: [],
      stratum: 0,
    };
    expect(runSouffle([f("Source", value)], [rule]).facts).toContainEqual(f("Copy", value));
  });
  it("uses native minimum-height provenance when a longer route is also possible", () => {
    const rules: Rule[] = [
      { id: "indirect", head: f("Target", "X"), body: [f("Mid", "X")], distinct: [], stratum: 0 },
      { id: "mid", head: f("Mid", "X"), body: [f("Source", "X")], distinct: [], stratum: 0 },
      { id: "direct", head: f("Target", "X"), body: [f("Source", "X")], distinct: [], stratum: 0 },
    ];
    const proof = explainSouffle([f("Source", "x")], rules, f("Target", "x"));
    expect(proof.children).toEqual([{ fact: 'Source("x")', kind: "input", children: [] }]);
  });
  it("returns true and false for ground queries and handles anonymous variables", () => {
    const state = new NovaRuntime().state;
    expect(terminalQuery(state, "?- Auditor(auditor_a).").rows).toEqual([[]]);
    expect(terminalQuery(state, "?- Auditor(missing).").rows).toEqual([]);
    expect(terminalQuery(state, "?- HasCap(_, C).").rows).toEqual([["hr_review"]]);
  });
  it("rejects unsafe rules and native directives without changing runtime input", () => {
    const state = new NovaRuntime().state;
    const before = structuredClone(state);
    expect(() => terminalQuery(state, "?- not Auditor(X).")).toThrow(/Soufflé/);
    expect(() => terminalQuery(state, '.include "/etc/passwd"')).toThrow();
    expect(state).toEqual(before);
  });
});
