import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { boundedEquivalence, dimacs } from "@rakazo/policy-runtime/bounded-equivalence";
import { factKey } from "@rakazo/policy-runtime/datalog";
import { testFiniteEquivalence } from "@rakazo/policy-runtime/finite-domain";
import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { readPolicyArtifact } from "../translated-policy.js";
import { novaComparison } from "./comparison-domain.js";
import { miniSatSolver } from "./sat-solver.js";
import { testNovaTraces } from "./trace-testing.js";

const { values } = parseArgs({
  options: {
    output: { type: "string" },
    artifact: { type: "string" },
    seed: { type: "string", default: "239" },
    cases: { type: "string", default: "512" },
    traces: { type: "string", default: "16" },
    steps: { type: "string", default: "12" },
    timeout: { type: "string", default: "10000" },
    cnf: { type: "boolean", default: false },
    native: { type: "boolean", default: false },
    testing: { type: "string", default: "sampled" },
  },
});
if (!values.output) throw new Error("Supply --output <new-directory>.");
if (values.testing !== "sampled" && values.testing !== "exhaustive")
  throw new Error("Choose --testing sampled or exhaustive.");
const output = resolve(values.output);
mkdirSync(output, { mode: 0o700 });
const save = (file: string, data: unknown) =>
  writeFileSync(resolve(output, file), `${JSON.stringify(data, null, 2)}\n`, { mode: 0o600 });
const artifacts = values.artifact
  ? [readFileSync(resolve(values.artifact), "utf8")]
  : [1, 2, 3].map((i) =>
      readFileSync(
        new URL(`../../evaluation/model-trials/trial-${i}.json`, import.meta.url),
        "utf8",
      ),
    );
const results = [];
for (const [index, source] of artifacts.entries()) {
  const policy = readPolicyArtifact(JSON.parse(source));
  const cases = [
    {
      name: "denial-with-prior-exposure-allowed",
      grouping: "fixed" as const,
      noPriorExposure: false,
      observables: ["DenyReceive"],
    },
    {
      name: "denial-no-prior-exposure",
      grouping: "fixed" as const,
      noPriorExposure: true,
      observables: ["DenyReceive"],
    },
    {
      name: "completion-variable-grouping",
      grouping: "variable" as const,
      noPriorExposure: true,
      observables: ["Finished"],
    },
  ];
  const comparisons = [];
  for (const scenario of cases) {
    const comparison = novaComparison(policy, scenario);
    const sat = boundedEquivalence(comparison, miniSatSolver(Number(values.timeout)), {
      capture: values.cnf
        ? (phase, cnf, inputs) => {
            writeFileSync(
              resolve(output, `trial-${index + 1}-${scenario.name}-${phase}.cnf`),
              dimacs(cnf),
              { mode: 0o600 },
            );
            save(`trial-${index + 1}-${scenario.name}-edb-variables.json`, inputs);
          }
        : undefined,
    });
    let nativeReplay: unknown;
    if (values.native && sat.status === "different" && sat.counterexample) {
      const select = (facts: { predicate: string; args: string[] }[]) =>
        facts.filter((f) => comparison.observables.includes(f.predicate));
      const observations = {
        reference: select(runSouffle(sat.counterexample.inputs, comparison.reference).facts),
        translated: select(runSouffle(sat.counterexample.inputs, comparison.translated).facts),
      };
      const keys = (facts: { predicate: string; args: string[] }[]) =>
        JSON.stringify(facts.map(factKey).sort());
      const passed =
        keys(observations.reference) === keys(sat.counterexample.reference) &&
        keys(observations.translated) === keys(sat.counterexample.translated);
      if (!passed) throw new Error("Native and TypeScript counterexample replay disagree.");
      nativeReplay = { ...observations, passed };
    }
    const testing = testFiniteEquivalence(comparison, {
      mode: values.testing,
      seed: Number(values.seed),
      cases: Number(values.cases),
    });
    comparisons.push({ ...scenario, space: comparison.space, sat, nativeReplay, testing });
    console.log(
      JSON.stringify({
        trial: index + 1,
        case: scenario.name,
        sat: sat.status,
        testing: testing.status,
      }),
    );
  }
  const traces = await testNovaTraces(policy, {
    seed: Number(values.seed),
    traces: Number(values.traces),
    steps: Number(values.steps),
  });
  results.push({
    artifactId: policy.id,
    artifactHash: createHash("sha256").update(source).digest("hex"),
    comparisons,
    traces,
  });
  save("results.json", {
    format: "nova-bounded-sat-v1",
    solver: "logic-solver 2.0.1 / MiniSat, offline isolated child",
    seed: Number(values.seed),
    results,
    scope:
      "SAT quantifies over all subsets of the declared optional EDB catalog satisfying explicit constraints; all other EDB tuples are absent. Full recursive stratified programs are used, not a UCQ approximation. UNSAT is bounded equality, not all-domain or all-trace equivalence. Every SAT witness is replayed and deletion-shrunk in the TypeScript evaluator; --native adds a Souffle cross-check. Testing and reachable trace checks remain separate.",
  });
}
