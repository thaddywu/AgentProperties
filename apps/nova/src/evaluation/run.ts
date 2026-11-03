import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { novaDocuments } from "../documents.js";
import { comparePrevention } from "../prevention.js";
import { FOUNDATION_ID, GOLDEN_ID, readPolicyArtifact } from "../translated-policy.js";
import { expressivenessPilot } from "./expressiveness.js";
import { localityPilot } from "./locality.js";
import { portabilityPilot } from "./portability.js";
import { translationPilot } from "./translation.js";
import { boundaryPilot, configurationPilot, workflowPilot } from "./workflows.js";

const { values } = parseArgs({
  options: { output: { type: "string" }, artifacts: { type: "string" } },
});
if (!values.output) throw new Error("Supply --output <new-output-directory>.");
const output = resolve(values.output);
mkdirSync(output, { mode: 0o700 });
const artifacts = values.artifacts
  ? resolve(values.artifacts)
  : fileURLToPath(new URL("../../evaluation/model-trials/", import.meta.url));
const save = (name: string, value: unknown) =>
  writeFileSync(resolve(output, name), `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
const progress = (phase: string) => console.log(JSON.stringify({ phase }));
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const sourceFiles = execFileSync(
  "git",
  [
    "ls-files",
    "--cached",
    "--others",
    "--exclude-standard",
    "--",
    "runtime/src",
    "apps/nova/src",
    "apps/nova/policy.md",
    "apps/nova/app.md",
    "apps/nova/tools.md",
    "apps/nova/agents",
    "apps/nova/evaluation",
    "translation/src",
  ],
  { cwd: root, encoding: "utf8" },
)
  .trim()
  .split("\n");
save("manifest.json", {
  format: "nova-research-pilot-v1",
  baselineCommit: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
  foundation: FOUNDATION_ID,
  reference: GOLDEN_ID,
  engines: {
    node: process.version,
    souffle: execFileSync("souffle", ["--version"], { encoding: "utf8" }).match(
      /Version: ([^\n]+)/,
    )?.[1],
  },
  sourceHashes: Object.fromEntries(
    sourceFiles.map((file) => [
      file,
      createHash("sha256")
        .update(readFileSync(resolve(root, file)))
        .digest("hex"),
    ]),
  ),
  study:
    "Exploratory pilot, not population coverage, universal proof, held-out accuracy, or an autonomous-agent study",
});
progress("portability");
save("portability.json", await portabilityPilot());
progress("expressiveness");
save("rq1.json", expressivenessPilot());
progress("reference-snapshots");
save("rq2-reference.json", translationPilot());
progress("boundary-probes");
save("boundaries.json", boundaryPilot());
save("configuration-reference.json", configurationPilot());
save("locality.json", localityPilot());
progress("disabled-workflows");
save("rq3-disabled.json", workflowPilot("disabled"));
progress("reference-workflows");
save("rq3-reference.json", workflowPilot("enforced"));
for (const file of readdirSync(artifacts)
  .filter((name) => /^trial-\d+\.json$/.test(name))
  .sort()) {
  const id = file.slice(0, -5);
  progress(`${id}-snapshots`);
  const artifact = readPolicyArtifact(JSON.parse(readFileSync(resolve(artifacts, file), "utf8")));
  const checks = comparePrevention(artifact);
  const eligible = checks.every(
    (test) => test.matches && test.golden.passed && test.translated?.passed,
  );
  save(`rq2-${id}.json`, {
    artifactId: artifact.id,
    model: artifact.model,
    exactDocumentsMatch: JSON.stringify(artifact.documents) === JSON.stringify(novaDocuments()),
    predefinedChecks: {
      passed: checks.filter((test) => test.matches && test.golden.passed && test.translated?.passed)
        .length,
      total: checks.length,
      eligible,
    },
    ...translationPilot(artifact),
  });
  save(`configuration-${id}.json`, configurationPilot(artifact));
  progress(`${id}-workflows`);
  save(
    `rq3-${id}.json`,
    eligible
      ? workflowPilot("enforced", artifact)
      : {
          status: "not-deployable",
          reason: "Existing installation cases rejected this artifact; no reference substitution",
        },
  );
}
progress("complete");
