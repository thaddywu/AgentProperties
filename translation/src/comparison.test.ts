import { spawnSync } from "node:child_process";
import type { PolicyFact } from "@rakazo/contracts";
import { REASONING_RULES } from "@rakazo/nova/policy";
import { describe, expect, it } from "vitest";
import { compareGenerated } from "./comparison.js";

const native = spawnSync("souffle", ["--version"]).status === 0;
const atom = (fact: PolicyFact) =>
  `${fact.predicate}(${fact.args.map((term) => (/^[A-Z]/.test(term) ? term : JSON.stringify(term))).join(", ")})`;
function referenceText(omit?: string) {
  // Reference-derived fixture is used only to test the comparator, never a model prompt or experiment.
  return REASONING_RULES.filter((rule) => rule.id !== omit)
    .map(
      (rule) =>
        `${atom(rule.head)} :- ${[
          ...rule.body.map((body) => `${body.negative ? "not " : ""}${atom(body)}`),
          ...rule.distinct.map(
            ([left, right]) => `${left} != ${/^[A-Z]/.test(right) ? right : JSON.stringify(right)}`,
          ),
        ].join(", ")}.`,
    )
    .join("\n");
}

describe.skipIf(!native)("post-generation local-store comparison", () => {
  it("matches a reference-derived fixture and detects a missing capability restriction", () => {
    const same = compareGenerated(referenceText());
    expect(same.length).toBeGreaterThan(10);
    expect(same.every((item) => item.passed)).toBe(true);
    const omitted = compareGenerated(referenceText("capability"));
    expect(omitted.find((item) => item.name === "hr-capability-absent")?.passed).toBe(false);
    expect(omitted.find((item) => item.name === "board-capability-not-exempt")?.passed).toBe(false);
  });
});
