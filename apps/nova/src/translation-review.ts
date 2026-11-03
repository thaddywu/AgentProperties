import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { novaDocuments } from "./documents.js";
import { REASONING_RULES } from "./policy.js";
import { comparePrevention } from "./prevention.js";
import type { NovaPolicyArtifact } from "./translated-policy.js";
import { readPolicyArtifact, ruleSource, rulesFor } from "./translated-policy.js";

// Human-maintained correspondence for the current Nova specification, not an equivalence claim.
const references: Record<string, { title: string; rules: string[]; protocol: string }> = {
  P1: {
    title: "Preserve information when forwarding",
    rules: ["trusted-label", "message-label", "runtime-dependency", "label-propagation"],
    protocol:
      "Send captures successful prior receipts and transfers this message's tags. Trusted source assignment is separate ingestion.",
  },
  P2: {
    title: "Require permission before receiving",
    rules: ["capability"],
    protocol:
      "The receiver checks its trusted capability configuration before delivery, including Board.",
  },
  P3: {
    title: "Prevent collecting three confidential parts",
    rules: ["three-tag-exposure", "three-tag-two-incoming", "three-tag-all-incoming"],
    protocol:
      "The receiver checks incoming tags together with its previously received information.",
  },
  P4: {
    title: "Keep refused content out of the recipient",
    rules: ["received-tag", "runtime-dependency"],
    protocol:
      "On denial, release no payload, add no Received facts, and remove temporary incoming tags. This needs runtime code as well as rules.",
  },
  P5: {
    title: "Combine audit coverage across reviewers",
    rules: ["coverage", "finished"],
    protocol:
      "Covered is derived locally. Only the global observer combines local coverage to compute Finished; no audit facts are sent to Board.",
  },
};
const policyText = (documents: NovaPolicyArtifact["documents"]) =>
  documents.find((doc) => doc.path === "policy.md")!.content;
export function policyCorrespondence(artifact: NovaPolicyArtifact) {
  const source = policyText(artifact.documents);
  const referenceSource = policyText(novaDocuments());
  const paragraphs = (text: string) =>
    text
      .trim()
      .split(/\r?\n\s*\r?\n/)
      .filter((part) => !part.startsWith("#"));
  return artifact.policies.map((policy, index) => {
    const reference = references[policy.id];
    return {
      id: policy.id,
      title: reference?.title ?? policy.id,
      source: paragraphs(source)[index] ?? "",
      referenceSource: paragraphs(referenceSource)[index] ?? "",
      inputMatchesReference: paragraphs(source)[index] === paragraphs(referenceSource)[index],
      golden: reference
        ? ruleSource(REASONING_RULES.filter((rule) => reference.rules.includes(rule.id)))
        : "",
      ruleIds: reference?.rules ?? [],
      protocol: reference?.protocol ?? "No current Nova reference mapping.",
      basis: policy.basis,
      generated: policy.datalog,
      notes: policy.notes,
    };
  });
}
/** Historical output remains inspectable, but cannot be installed or rerun under a new protocol. */
export function savedTranslationReview(): PolicyReview {
  const artifact = JSON.parse(
    readFileSync(new URL("../demo/translation.json", import.meta.url), "utf8"),
  ) as NovaPolicyArtifact;
  const { id, ...content } = artifact;
  if (
    id !== "5f15c1a29882a59d9ea0a7049987bcf5f50e10f3ec4fd731f2ee65383042b685" ||
    createHash("sha256").update(JSON.stringify(content)).digest("hex") !== id
  )
    throw new Error("Saved historical artifact identity mismatch.");
  const saved = JSON.parse(
    readFileSync(new URL("../demo/review.json", import.meta.url), "utf8"),
  ) as {
    artifactId: string;
    cases: PolicyReview["cases"];
    correspondence: PolicyReview["correspondence"];
  };
  if (saved.artifactId !== id) throw new Error("Saved review does not match artifact.");
  return {
    artifact,
    cases: saved.cases,
    correspondence: saved.correspondence,
    eligible: false,
    historical: true,
    semanticCorrectness: "unproven",
  };
}
export function reviewPolicy(input: unknown) {
  const artifact = readPolicyArtifact(input);
  runSouffle([], rulesFor({ policy: artifact }));
  const cases = comparePrevention(artifact);
  return {
    artifact,
    cases,
    correspondence: policyCorrespondence(artifact),
    eligible: cases.every((test) => test.matches && test.golden.passed && test.translated?.passed),
    historical: false,
    semanticCorrectness: "unproven" as const,
  };
}
export type PolicyReview = ReturnType<typeof reviewPolicy>;
