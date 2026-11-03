import { expect, it } from "vitest";
import { compileQuestion, QUESTIONS } from "../src/questions.js";
import { NovaService } from "../src/service.js";
import { ACTION_PRESET, PREVENTABLE_PRESET } from "../src/shared.js";

it("runs all concrete catalog examples on the pending HR snapshot without changing it", () => {
  const service = new NovaService();
  const before = service.runtime.snapshot();
  for (const q of QUESTIONS) {
    if (!("tab" in q)) continue;
    const result = service.run({
      operation: q.tab,
      revision: 1,
      scope: q.scope,
      query: q.query,
      remove: q.remove,
      events: q.events ?? PREVENTABLE_PRESET,
      add: q.add,
      goal: q.goal,
      basis: q.basis,
      actions: q.actions ?? ACTION_PRESET,
    }) as { rows?: string[][]; result?: boolean; size?: number };
    expect(result).not.toBeNull();
    if (q.tab === "query" && q.id !== "completion") expect(result.rows!.length).toBeGreaterThan(0);
    if (q.id === "completion") expect(result.rows).toEqual([]);
    if (q.id === "without-receive") expect(result.result).toBe(false);
    if (q.id === "prevention") expect(result.size).toBe(1);
    if (q.id === "missing-permission") expect(result.rows).toEqual([["hr_review"]]);
  }
  expect(service.runtime.snapshot()).toEqual(before);
  expect(QUESTIONS.filter((q) => !("tab" in q))).toHaveLength(0);
});

it("executes interpreted arguments, not fixed terminal defaults", () => {
  const service = new NovaService();
  const state = service.state();
  const context = { tags: ["nova_hiring"], goalGroups: ["nova"], messages: state.messages };
  const before = service.runtime.snapshot();
  const whatIf = compileQuestion(
    "without-receive",
    { recipient: "auditor_a", message: "mH", earlierMessage: "mP" },
    context,
  );
  expect(whatIf.remove).toBe('Received("auditor_a", "mP").');
  expect(whatIf.add).toBe("");
  expect(
    service.run({
      operation: whatIf.tab,
      revision: 1,
      query: whatIf.query,
      remove: whatIf.remove,
      add: whatIf.add,
    }),
  ).toMatchObject({ result: false });
  const minimum = compileQuestion(
    "prevention",
    { recipient: "auditor_a", message: "mH", eventMessages: ["mF"] },
    context,
  );
  expect(minimum.events).toBe('event1:\n  Received("auditor_a", "mF").');
  expect(
    service.run({
      operation: minimum.tab,
      revision: 1,
      query: minimum.query,
      events: minimum.events,
    }),
  ).toMatchObject({ size: 1, solutions: [["event1"]] });
  const plan = compileQuestion(
    "planning",
    { goalGroup: "nova", basis: "earlier", routes: ["facility->auditor_b", "hr->auditor_a"] },
    context,
  );
  expect(plan.actions).toBe("facility->auditor_b\nhr->auditor_a");
  expect(
    service.run({
      operation: plan.tab,
      revision: 1,
      goal: plan.goal,
      basis: plan.basis,
      actions: plan.actions,
    }),
  ).toMatchObject({ trace: [{ id: "facility->auditor_b" }, { id: "hr->auditor_a" }] });
  expect(service.runtime.snapshot()).toEqual(before);
});

it("rejects invalid action domains and event candidates without silently substituting defaults", () => {
  const service = new NovaService();
  const context = {
    tags: ["nova_hiring"],
    goalGroups: ["nova"],
    messages: service.state().messages,
  };
  for (const parameters of [
    { recipient: "auditor_a", message: "mH", eventMessages: [] },
    { recipient: "auditor_a", message: "mH", eventMessages: ["mF", "mF"] },
    { recipient: "auditor_a", message: "mH", eventMessages: ["m0"] },
  ])
    expect(() => compileQuestion("prevention", parameters, context)).toThrow();
  for (const parameters of [
    { goalGroup: "nova", basis: "earlier", routes: ["board->auditor_a"] },
    { goalGroup: "unknown", basis: "earlier", routes: ["hr->auditor_a"] },
    { goalGroup: "nova", basis: "selected", routes: ["hr->auditor_a"] },
  ])
    expect(() => compileQuestion("planning", parameters, context)).toThrow();
});
