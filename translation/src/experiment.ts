import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { ApplicationDocuments, NaturalLanguagePolicy } from "./application.js";
import { extractPolicies } from "./application.js";
import { buildPrompt, TRANSLATION_INSTRUCTIONS } from "./prompt.js";
import { validateDatalog } from "./validation.js";

export type GeneratedPolicy = { id: string; datalog: string; notes: string };

export function parseModelOutput(
  raw: string,
  policies: NaturalLanguagePolicy[],
): GeneratedPolicy[] {
  const json = raw.trim().replace(/^```(?:json)?\s*\n([\s\S]*?)\n```$/, "$1");
  const value: unknown = JSON.parse(json);
  if (
    !value ||
    typeof value !== "object" ||
    !("policies" in value) ||
    !Array.isArray(value.policies)
  )
    throw new Error("Expected a JSON object with a policies array.");
  const entries: GeneratedPolicy[] = [];
  for (const item of value.policies) {
    if (
      !item ||
      typeof item.id !== "string" ||
      typeof item.datalog !== "string" ||
      typeof item.notes !== "string"
    )
      throw new Error("Each policy needs string id, datalog and notes.");
    if (
      !policies.some((policy) => policy.id === item.id) ||
      entries.some((entry) => entry.id === item.id)
    )
      throw new Error("Unknown or duplicate policy ID in model output.");
    entries.push({ id: item.id, datalog: item.datalog, notes: item.notes });
  }
  if (entries.length !== policies.length)
    throw new Error("Model omitted one or more input policies.");
  return entries;
}

export async function runExperiment(options: {
  documents: ApplicationDocuments;
  output: string;
  metadata: Record<string, unknown>;
  generate: (prompt: string, record: (raw: string) => void) => Promise<string>;
}) {
  mkdirSync(options.output, { recursive: false, mode: 0o700 });
  const save = (name: string, content: string) =>
    writeFileSync(join(options.output, name), content, { mode: 0o600 });
  const json = (name: string, value: unknown) => save(name, `${JSON.stringify(value, null, 2)}\n`);
  const policies = extractPolicies(
    options.documents.find((doc) => doc.path === "policy.md")!.content,
  );
  const prompt = buildPrompt(options.documents);
  let revision: string | null = null;
  try {
    revision = execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    /* Source snapshots remain sufficient outside Git. */
  }
  json("input-documents.json", options.documents);
  save("prompt.txt", prompt);
  save("system-prompt.txt", TRANSLATION_INSTRUCTIONS);
  json("metadata.json", {
    ...options.metadata,
    startedAt: new Date().toISOString(),
    revision,
    referenceRulesInPrompt: false,
    translationAttempts: 1,
  });
  save("raw-response.txt", "");
  save("generated.dl", "");
  let result: Record<string, unknown>;
  try {
    const raw = await options.generate(prompt, (text) => save("raw-response.txt", text));
    save("raw-response.txt", raw); // Always persisted before JSON parsing or validation.
    const generated = parseModelOutput(raw, policies);
    const datalog = generated.map((policy) => `// ${policy.id}\n${policy.datalog}`).join("\n\n");
    save("generated.dl", datalog);
    const validation = validateDatalog(datalog);
    let comparison: unknown = null;
    let comparisonError: string | null = null;
    if (validation.status === "valid_translation_output") {
      try {
        const { compareGenerated } = await import("./comparison.js");
        comparison = compareGenerated(datalog);
      } catch (error) {
        comparisonError = String(error);
      }
    }
    const missingRules = generated
      .filter((policy) => !policy.datalog.trim())
      .map((policy) => policy.id);
    const mismatches = Array.isArray(comparison) && comparison.some((item) => !item.passed);
    result = {
      status:
        validation.status === "valid_translation_output" &&
        (mismatches || missingRules.length || comparisonError)
          ? "potential_semantic_mismatch"
          : validation.status,
      policies: generated.map((policy) => ({
        ...policy,
        source: policies.find((p) => p.id === policy.id)!.text,
      })),
      validation,
      missingRules,
      comparison,
      comparisonError,
      semanticCorrectness: "unproven",
      limitations: [
        "Local-store probes only; no runtime installation or end-to-end enforcement test.",
        "Compilation is not proof of semantic equivalence.",
        "Payload release, atomicity and protocol facts require existing runtime behavior; rules alone cannot establish them.",
        "No automatic repair or reference-rule substitution.",
      ],
    };
  } catch (error) {
    result = {
      status: "model_or_parsing_failure",
      error: String(error),
      semanticCorrectness: "unproven",
    };
  }
  json("results.json", result);
  const comparisons = Array.isArray(result.comparison) ? result.comparison : [];
  const observations = comparisons.filter((item) => !item.passed).map((item) => item.name);
  const policyNotes = Array.isArray(result.policies)
    ? result.policies
        .map((policy) => `- ${policy.id}: ${policy.notes || "No model notes."}`)
        .join("\n")
    : "No parsed policy output.";
  save(
    "report.md",
    `# Nova translation experiment\n\nStatus: ${result.status}.\n\n${result.error ?? "See results.json for per-policy output and validation."}\n\nValidation:\n\n${JSON.stringify(result.validation ?? {}, null, 2)}\n\nLocal-store probes: ${comparisons.length} run, ${observations.length} mismatched. ${observations.length ? `Mismatches: ${observations.join(", ")}.` : "No semantic equivalence claim."}\n\nModel notes (unverified):\n\n${policyNotes}\n\n${result.comparisonError ?? ""}\n\nSemantic correctness is unproven. Reference rules were not supplied to the model. Any post-generation comparison is a limited set of local-store probes, not runtime integration. Payload release and other protocol guarantees still depend on the existing runtime.\n`,
  );
  return result;
}
