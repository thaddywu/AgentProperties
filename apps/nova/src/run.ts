import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { comparePrevention } from "./prevention.js";
import { createEpisode } from "./runtime.js";
import { GOLDEN_ID, readPolicyArtifact } from "./translated-policy.js";

// Same actual transitions as the UI. Comparisons never change an existing session.
const { values } = parseArgs({
  options: { policy: { type: "string" }, compare: { type: "boolean" } },
});
const policy = values.policy
  ? readPolicyArtifact(JSON.parse(readFileSync(values.policy, "utf8")))
  : undefined;
const cases = policy || values.compare ? comparePrevention(policy) : undefined;
if (values.compare) {
  console.log(
    JSON.stringify(
      { mode: policy ? "translated" : "golden", policyId: policy?.id ?? GOLDEN_ID, cases },
      null,
      2,
    ),
  );
  if (
    cases!.some(
      (test) => !test.golden.passed || (policy && (!test.matches || !test.translated?.passed)),
    )
  )
    process.exitCode = 1;
} else if (
  policy &&
  cases!.some((test) => !test.matches || !test.golden.passed || !test.translated?.passed)
) {
  console.error(
    "Translated policy failed prevention checks. Use --compare to inspect counterexamples; no demo session was started.",
  );
  process.exitCode = 1;
} else {
  const runtime = createEpisode("denial", policy);
  const pending = runtime.state.messages.find((message) => message.status === "pending");
  if (!pending) throw new Error("The Nova denial scenario must have a pending message.");
  const decision = runtime.settle(pending.id);
  console.log(
    JSON.stringify(
      {
        mode: policy ? "translated" : "golden",
        policyId: policy?.id ?? GOLDEN_ID,
        scenario: "third-part-denied",
        allowed: decision.allowed,
        message: pending.id,
        recipient: pending.to,
        events: runtime.state.events.length,
        payloadVisible: runtime.accessible(pending.to).some((message) => message.id === pending.id),
      },
      null,
      2,
    ),
  );
  if (decision.allowed) process.exitCode = 1;
}
