import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { runNovaPortDemo } from "./port-demo.js";
import { readPolicyArtifact } from "./translated-policy.js";

const { values } = parseArgs({
  options: { output: { type: "string" }, artifact: { type: "string" } },
});
if (!values.output) throw new Error("Supply --output <new-output-directory>.");
const output = resolve(values.output);
mkdirSync(output, { mode: 0o700 });
const policy = values.artifact
  ? readPolicyArtifact(JSON.parse(readFileSync(values.artifact, "utf8")))
  : undefined;
const result = await runNovaPortDemo(policy);
writeFileSync(resolve(output, "results.json"), `${JSON.stringify(result, null, 2)}\n`, {
  mode: 0o600,
});
console.log(
  JSON.stringify({
    plans: result.optimized.plansExamined,
    witnesses: result.optimized.witnessesChecked,
    baselineCost: result.baseline.cost,
    optimizedCost: result.optimized.cost,
    auditComplete: result.execution.auditComplete,
    reportPublished: result.fsm.published,
  }),
);
