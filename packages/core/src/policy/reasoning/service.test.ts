import { describe, expect, it } from "vitest";
import { ACTION_PRESET } from "./analysis.js";
import { NovaService } from "./service.js";

describe("Nova local service", () => {
  it("rejects stale requests and keeps read-only analysis input state unchanged", () => {
    const service = new NovaService(),
      before = JSON.stringify(service.runtime.state);
    expect(() =>
      service.run({ operation: "why", revision: 0, query: "DenyReceive(auditor_a, mH)" }),
    ).toThrow(/changed/);
    service.run({
      operation: "what-if",
      revision: 1,
      remove: "Received(auditor_a, mF). Receiver(auditor_a, mF).",
      query: "DenyReceive(auditor_a, mH)",
    });
    expect(JSON.stringify(service.runtime.state)).toBe(before);
  });
  it("queries actual receive snapshots and preserves gate inputs after a denial", () => {
    const service = new NovaService();
    const before = service.run({
      operation: "query",
      revision: 1,
      event: 10,
      side: "before",
      query: "?- Received(auditor_a, mF).",
    });
    const after = service.run({
      operation: "query",
      revision: 1,
      event: 10,
      side: "after",
      query: "?- Received(auditor_a, mF).",
    });
    expect(before).toMatchObject({ rows: [] });
    expect(after).toMatchObject({ rows: [[]] });
    service.run({ operation: "settle", revision: 1, id: "mH" });
    expect(
      service.run({
        operation: "why",
        revision: 2,
        event: 12,
        side: "check",
        query: "DenyReceive(auditor_a, mH)",
      }),
    ).toMatchObject({ rule: "three-part-exposure" });
    expect(
      service.run({ operation: "why", revision: 2, query: "DenyReceive(auditor_a, mH)" }),
    ).toBeNull();
  });
  it("keeps an explicit earlier-state search separate and commits a returned trace through runtime", () => {
    const service = new NovaService();
    const before = JSON.stringify(service.runtime.state);
    const result = service.run({
      operation: "speculative",
      revision: 1,
      basis: "earlier",
      actions: ACTION_PRESET,
      goal: "Finished(nova)",
    }) as { trace: { id: string }[] };
    expect(JSON.stringify(service.runtime.state)).toBe(before);
    const replay = service.run({
      operation: "replay-trace",
      revision: 1,
      basis: "earlier",
      trace: result.trace.map((a) => a.id),
    });
    expect(replay).toMatchObject({ finished: true, version: 2 });
  });
  it("executes sends before receives and generates its input facts at each transition", () => {
    const service = new NovaService();
    service.run({ operation: "reset", preset: "initial", revision: 1 });
    service.run({ operation: "advance", revision: 2 });
    expect(service.state().records.some((r) => r.fact.predicate === "Sender")).toBe(true);
    expect(service.state().records.some((r) => r.fact.predicate === "Received")).toBe(false);
    service.run({ operation: "advance", revision: 3 });
    expect(service.state().records.some((r) => r.fact.predicate === "Received")).toBe(true);
    expect(
      service
        .state({ event: 1, side: "check" })
        .records.some((r) => r.fact.predicate === "Incoming"),
    ).toBe(true);
  });
  it("rejects derived config and rolls back a failed speculative replay", () => {
    const service = new NovaService(),
      before = JSON.stringify(service.runtime.state);
    expect(() =>
      service.run({ operation: "config", revision: 1, config: "Finished(nova)." }),
    ).toThrow(/read-only/);
    expect(() =>
      service.run({
        operation: "replay-trace",
        revision: 1,
        basis: "earlier",
        trace: ["facility->auditor_a", "hr->auditor_a"],
      }),
    ).toThrow(/denied/);
    expect(JSON.stringify(service.runtime.state)).toBe(before);
  });
});
