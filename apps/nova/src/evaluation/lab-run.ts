import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { encodeRule } from "@rakazo/policy-runtime/query";
import { rulesFor } from "../translated-policy.js";
import { expressivenessPilot } from "./expressiveness.js";
import { recordedPolicy } from "./recorded-policy.js";
import { recursiveComparison } from "./recursive.js";
import { createRoutingEpisode } from "./routing-agent.js";
import { translationPilot } from "./translation.js";
import { compareUcq } from "./ucq.js";
import { configurationPilot } from "./workflows.js";

const { values } = parseArgs({ options: { output: { type: "string" } } });
if (!values.output) throw new Error("Supply --output <new-directory>.");
const output = resolve(values.output);
mkdirSync(output, { mode: 0o700 });
const save = (name: string, value: unknown) =>
  writeFileSync(resolve(output, name), `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
save("rq1.json", expressivenessPilot());
const reference = rulesFor({}).map(encodeRule);
const referenceConfiguration = configurationPilot();
const results = [];
for (let trial = 1; trial <= 3; trial++) {
  const source = readFileSync(
    new URL(`../../evaluation/model-trials/trial-${trial}.json`, import.meta.url),
    "utf8",
  );
  const artifact = recordedPolicy(JSON.parse(source));
  const translated = rulesFor({ policy: artifact });
  const result = {
    trial,
    artifactId: artifact.id,
    artifactHash: createHash("sha256").update(source).digest("hex"),
    coverageFragment: compareUcq(
      reference.filter((r) => r.head.predicate === "Covered"),
      translated.filter((r) => r.head.predicate === "Covered"),
      "Covered",
    ),
    wholeReceiveProgram: compareUcq(
      reference.filter((r) => r.head.predicate === "Deny"),
      translated.filter((r) => r.head.predicate === "Deny"),
      "Deny",
    ),
    snapshots: translationPilot(artifact),
    recursive: recursiveComparison(artifact),
    reachableConfigurationCounterexample: {
      reference: referenceConfiguration,
      translated: configurationPilot(artifact),
    },
  };
  results.push(result);
  console.log(JSON.stringify({ trial, phase: "rq2-complete" }));
}
save("rq2.json", {
  observables: {
    enforcement: ["Deny"],
    task: ["Covered", "Finished"],
    information: ["Knows"],
  },
  scope:
    "The exact UCQ coverage fragment treats MessageTag as a leaf relation; full Nova has recursion, negation and comparisons. Finite tests are not universal equivalence. The three artifacts and exploratory counterexample domain predate this lab; no held-out accuracy claim.",
  trials: results,
  recursionControl: recursiveComparison(
    recordedPolicy(
      JSON.parse(
        readFileSync(
          new URL("../../evaluation/model-trials/trial-1.json", import.meta.url),
          "utf8",
        ),
      ),
    ),
    true,
  ),
});
const scripted = [];
for (const mode of ["disabled", "reference"] as const) {
  const episode = await createRoutingEpisode(mode);
  for (const sender of ["procurement", "facility", "hr"])
    await episode.attempt({ sender, recipient: "auditor_a" });
  if (episode.view().remaining.includes("hr"))
    await episode.attempt({ sender: "hr", recipient: "auditor_b" });
  scripted.push({ condition: mode, ...episode.result(), modelCalls: 0, modelTokens: 0 });
}
save("rq3-scripted.json", {
  scope:
    "Positive control: three reports to A, then HR to B after rejection. This intentionally bad script has no model and cannot estimate model token overhead. Safe alternative routing is checked separately.",
  episodes: scripted,
});
console.log(JSON.stringify({ phase: "complete" }));
