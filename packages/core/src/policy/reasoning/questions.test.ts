import { expect, it } from "vitest";
import { QUESTIONS } from "./questions.js";
import { NovaService } from "./service.js";
import { PREVENTABLE_PRESET } from "./shared.js";

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
      events: PREVENTABLE_PRESET,
    }) as { rows?: string[][]; result?: boolean; size?: number };
    expect(result).not.toBeNull();
    if (q.tab === "query") expect(result.rows!.length).toBeGreaterThan(0);
    if (q.id === "without-receive") expect(result.result).toBe(false);
    if (q.id === "prevention") expect(result.size).toBe(1);
    if (q.id === "missing-permission") expect(result.rows).toEqual([["hr_review"]]);
  }
  expect(service.runtime.snapshot()).toEqual(before);
  expect(QUESTIONS.filter((q) => !("tab" in q))).toHaveLength(3);
});
