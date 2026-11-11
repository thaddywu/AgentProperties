import catalog from "../python/policy_runtime/foundations.json" with { type: "json" };
import type { Rule } from "./datalog.js";

type FoundationPredicate = { kind: "input" | "derived"; args: string[]; meaning: string };
const schemas = <T extends Record<string, unknown>>(value: T) =>
  value as { [K in keyof T]: FoundationPredicate };

export const CAPABILITY_PREDICATES = schemas(catalog.capability.predicates);
export const CAPABILITY_RULES = catalog.capability.rules as Rule[];
export const PROVENANCE_PREDICATES = schemas(catalog.provenance.predicates);
export const PROVENANCE_RULES = catalog.provenance.rules as Rule[];
export const FOUNDATIONS = {
  capability: { predicates: CAPABILITY_PREDICATES, rules: CAPABILITY_RULES },
  provenance: { predicates: PROVENANCE_PREDICATES, rules: PROVENANCE_RULES },
};
