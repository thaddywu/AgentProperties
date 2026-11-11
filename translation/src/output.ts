import type { NaturalLanguagePolicy } from "./application.js";

export type GeneratedPolicy = { id: string; datalog: string; notes: string };

/** Planned translation permits one rule to cover several reviewed requirements. */
export function parsePlannedModelOutput(raw: string, targets: NaturalLanguagePolicy[]) {
  const value = JSON.parse(raw.trim().replace(/^```(?:json)?\s*\n([\s\S]*?)\n```$/, "$1"));
  if (
    !value ||
    !Array.isArray(value.rules) ||
    !Array.isArray(value.coverage) ||
    value.rules.length > 99
  )
    throw new Error("Expected shared rules and requirement coverage arrays.");
  const rules: { id: string; datalog: string }[] = [];
  for (const rule of value.rules) {
    if (
      !rule ||
      typeof rule.id !== "string" ||
      !/^[a-z][a-z0-9_-]{0,63}$/.test(rule.id) ||
      rules.some((r) => r.id === rule.id) ||
      typeof rule.datalog !== "string" ||
      !rule.datalog.trim()
    )
      throw new Error("Each shared rule needs a distinct ID and nonempty Datalog.");
    rules.push({ id: rule.id, datalog: rule.datalog });
  }
  const coverage: { id: string; ruleIds: string[]; notes: string }[] = [];
  for (const entry of value.coverage) {
    if (
      !entry ||
      !targets.some((t) => t.id === entry.id) ||
      coverage.some((c) => c.id === entry.id) ||
      typeof entry.notes !== "string" ||
      !Array.isArray(entry.ruleIds) ||
      !entry.ruleIds.length ||
      new Set(entry.ruleIds).size !== entry.ruleIds.length ||
      entry.ruleIds.some((id: unknown) => !rules.some((r) => r.id === id))
    )
      throw new Error("Each Datalog target must reference existing shared rules exactly once.");
    coverage.push({ id: entry.id, ruleIds: entry.ruleIds, notes: entry.notes });
  }
  if (
    coverage.length !== targets.length ||
    rules.some((r) => !coverage.some((c) => c.ruleIds.includes(r.id)))
  )
    throw new Error("Missing requirement coverage or unreferenced generated rule.");
  const policies = coverage.map((c) => ({
    id: c.id,
    notes: c.notes,
    datalog: rules
      .filter((r) => c.ruleIds.includes(r.id))
      .map((r) => r.datalog)
      .join("\n"),
  }));
  return { rules, coverage, policies };
}

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
