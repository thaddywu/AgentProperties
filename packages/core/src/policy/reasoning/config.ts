import type { PolicyFact } from "@rakazo/contracts";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });

export const CONFIG = [
  f("TagGroup", "nova_procurement", "nova"),
  f("TagGroup", "nova_facility", "nova"),
  f("TagGroup", "nova_hiring", "nova"),
  f("AuditGoal", "nova", "nova_procurement", "nova_facility", "nova_hiring"),
  f("Auditor", "auditor_a"),
  f("Auditor", "auditor_b"),
  f("HasCap", "auditor_a", "hr_review"),
  f("HasCap", "hr", "hr_review"),
  f("Requires", "nova_hiring", "hr_review"),
];
