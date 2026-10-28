import type { NaturalLanguagePolicy } from "./application.js";

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
