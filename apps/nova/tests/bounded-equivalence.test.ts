import { readFileSync } from "node:fs";
import { boundedEquivalence } from "@rakazo/policy-runtime/bounded-equivalence";
import type { FiniteComparison, FiniteSchema } from "@rakazo/policy-runtime/finite-domain";
import { testFiniteEquivalence } from "@rakazo/policy-runtime/finite-domain";
import { parsePolicyRules } from "@rakazo/policy-runtime/query";
import { describe, expect, it, vi } from "vitest";
import { novaComparison } from "../src/evaluation/comparison-domain.js";
import { recordedPolicy } from "../src/evaluation/recorded-policy.js";
import { miniSatSolver } from "../src/evaluation/sat-solver.js";
import { testNovaTraces } from "../src/evaluation/trace-testing.js";

const f = (predicate: string, ...args: string[]) => ({ predicate, args });
const schema: FiniteSchema = {
  Seed: { kind: "input", args: ["X"] },
  Blocked: { kind: "input", args: ["X"] },
  Base: { kind: "input", args: ["X"] },
  Edge: { kind: "input", args: ["X", "Y"] },
  Helper: { kind: "derived", args: ["X"] },
  Reach: { kind: "derived", args: ["X", "Y"] },
  Out: { kind: "derived", args: ["X"] },
  Gate: { kind: "input", args: [] },
  Flag: { kind: "derived", args: [] },
};
const comparison = (
  reference: string,
  translated: string,
  optional = [f("Seed", "a"), f("Blocked", "a")],
): FiniteComparison => ({
  schema,
  reference: parsePolicyRules(reference),
  translated: parsePolicyRules(translated),
  observables: ["Out"],
  space: { required: [], optional },
});
const policy = () =>
  recordedPolicy(
    JSON.parse(
      readFileSync(new URL("../evaluation/model-trials/trial-1.json", import.meta.url), "utf8"),
    ),
  );

describe("finite SAT encoding and differential testing", () => {
  it("agrees with exhaustive evaluator truth tables for recursion, negation, inequalities and projection", () => {
    const programs = [
      comparison("Out(X) :- Seed(X), not Blocked(X).", "Out(X) :- Seed(X)."),
      comparison("Out(X) :- Seed(X). Out(X) :- Out(X).", "Out(X) :- Seed(X)."),
      comparison(
        'Reach(X,Y) :- Edge(X,Y). Reach(X,Z) :- Reach(X,Y), Edge(Y,Z). Out(Y) :- Reach("a",Y).',
        'Out(Y) :- Edge("a",Y).',
        [f("Edge", "a", "b"), f("Edge", "b", "c"), f("Edge", "b", "a")],
      ),
      comparison("Out(X) :- Edge(X,Y), X != Y.", "Out(X) :- Edge(X,Y).", [
        f("Edge", "a", "a"),
        f("Edge", "a", "b"),
      ]),
      comparison(
        "Helper(X) :- Seed(X). Out(X) :- Helper(X).",
        "Reach(X,X) :- Seed(X). Out(X) :- Seed(X).",
      ),
      comparison('Out("Upper") :- Seed("Upper").', "Out(X) :- Seed(X).", [f("Seed", "Upper")]),
    ];
    const strata = comparison(
      "Helper(X) :- Seed(X), not Blocked(X). Out(X) :- Base(X), not Helper(X).",
      "Out(X) :- Base(X), not Seed(X). Out(X) :- Base(X), Blocked(X).",
    );
    strata.space.required = [f("Base", "a")];
    programs.push(strata);
    const boolean = comparison("Flag() :- not Gate().", "Flag() :- Gate().", [f("Gate")]);
    boolean.observables = ["Flag"];
    programs.push(boolean);
    programs.push(
      comparison(
        'Out("é") :- Seed("é"). Out("é") :- Seed("é").',
        'Out("é") :- Seed("é"). Out("é") :- Seed("é").',
        [f("Seed", "é"), f("Seed", "é")],
      ),
    );
    for (const input of programs) {
      const expected = testFiniteEquivalence(input, { mode: "exhaustive", cases: 64 });
      const actual = boundedEquivalence(input, miniSatSolver());
      expect(actual.status).toBe(expected.status);
      if (actual.status === "different") {
        expect(actual.counterexample?.replayVerified).toBe(true);
        expect(actual.counterexample?.different).toBe(true);
      }
    }
  });
  it("does not let seedless recursive cycles prove themselves", () => {
    const input = comparison("Out(X) :- Seed(X). Out(X) :- Out(X).", "");
    input.space.constraints = [[{ fact: f("Seed", "a"), present: false }]];
    expect(boundedEquivalence(input, miniSatSolver()).status).toBe("equivalent_within_bound");
    expect(testFiniteEquivalence(input, { mode: "exhaustive", cases: 8 }).status).toBe(
      "equivalent_within_bound",
    );
  });
  it("distinguishes an empty domain, unsupported program, timeout, invalid model and exhausted budget", () => {
    const input = comparison("Out(X) :- Seed(X).", "Out(X) :- Seed(X).");
    input.space.constraints = [
      [{ fact: f("Seed", "a"), present: true }],
      [{ fact: f("Seed", "a"), present: false }],
    ];
    expect(boundedEquivalence(input, miniSatSolver()).status).toBe("empty_domain");
    expect(testFiniteEquivalence(input, { mode: "exhaustive", cases: 8 }).status).toBe(
      "empty_domain",
    );
    const recursive = comparison(
      'Reach(X,Y) :- Edge(X,Y). Reach(X,Z) :- Reach(X,Y), Edge(Y,Z). Out(Y) :- Reach("a",Y).',
      'Out(Y) :- Edge("a",Y).',
      [f("Edge", "a", "b"), f("Edge", "b", "c")],
    );
    expect(boundedEquivalence(recursive, miniSatSolver(), { quotas: { rounds: 1 } }).status).toBe(
      "inconclusive",
    );
    expect(
      boundedEquivalence(recursive, () => ({ status: "unknown", reason: "timeout" })).status,
    ).toBe("inconclusive");
    expect(boundedEquivalence(recursive, () => ({ status: "sat", trueVariables: [] })).status).toBe(
      "inconclusive",
    );
    expect(
      boundedEquivalence(recursive, miniSatSolver(), { quotas: { operations: 1 } }).status,
    ).toBe("inconclusive");
    expect(
      boundedEquivalence(recursive, miniSatSolver(), { quotas: { variables: 1 } }).status,
    ).toBe("inconclusive");
    expect(boundedEquivalence(recursive, miniSatSolver(), { quotas: { clauses: 1 } }).status).toBe(
      "inconclusive",
    );
    const solver = vi.fn(miniSatSolver());
    const invalid = comparison(
      "Out(X) :- Base(X), not Helper(X). Helper(X) :- Base(X), not Out(X).",
      "",
    );
    expect(boundedEquivalence(invalid, solver).status).toBe("unsupported");
    expect(solver).not.toHaveBeenCalled();
    const forged = comparison("Out(X) :- Seed(X).", "");
    forged.space.required = [f("Out", "a")];
    expect(boundedEquivalence(forged, solver).status).toBe("unsupported");
  });
  it("checks full Nova and independently exhausts the constrained 13-tuple domain", () => {
    const all = novaComparison(policy(), {
      grouping: "fixed",
      noPriorExposure: false,
      observables: ["Deny"],
    });
    const witness = boundedEquivalence(all, miniSatSolver());
    expect(witness.status).toBe("different");
    expect(witness.counterexample?.shrink.deletionMinimal).toBe(true);
    const constrained = novaComparison(policy(), {
      grouping: "fixed",
      noPriorExposure: true,
      observables: ["Deny"],
    });
    expect(boundedEquivalence(constrained, miniSatSolver()).status).toBe("equivalent_within_bound");
    const exhaustive = testFiniteEquivalence(constrained, { mode: "exhaustive", cases: 8192 });
    expect(exhaustive.status).toBe("equivalent_within_bound");
    expect(exhaustive.admitted).toBe(7168);
    expect(exhaustive.examined).toBe(8192);
    const completion = novaComparison(policy(), {
      grouping: "variable",
      noPriorExposure: true,
      observables: ["Finished"],
    });
    expect(boundedEquivalence(completion, miniSatSolver()).status).toBe("different");
    const sampled = testFiniteEquivalence(all, { mode: "sampled", seed: 239, cases: 512 });
    expect(sampled).toEqual(testFiniteEquivalence(all, { mode: "sampled", seed: 239, cases: 512 }));
    expect(sampled.status).toBe("different");
  });
  it("reproduces a task-output difference using actual shared-port traces", async () => {
    const result = await testNovaTraces(policy(), { seed: 239, traces: 4, steps: 12 });
    expect(result.tracesWithDifference).toBe(2);
    expect(result.checkedSteps).toBe(30);
    expect(result.counterexamples).toHaveLength(2);
    expect(result).toEqual(await testNovaTraces(policy(), { seed: 239, traces: 4, steps: 12 }));
  });
});
