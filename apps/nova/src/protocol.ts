import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { MESSAGING_PROTOCOL } from "@rakazo/policy-runtime/messaging-protocol";

/** @self binds to the store's principal; _ matches any value.
 * Placement governs actual local engine input/output, not just UI labels.
 * Shared config is explicitly copied into every local store.
 */
export const PROTOCOL = {
  replicated: ["Auditor", ...MESSAGING_PROTOCOL.replicated, "AuditGoal"],
  local: {
    ...MESSAGING_PROTOCOL.local,
    Audited: ["_"],
    AuditReceipt: ["_", "_"],
    Finished: ["_"],
  } as Record<string, string[]>,
  onlyAt: { TrustedSource: "board", AuditReceipt: "board", Finished: "board" } as Record<
    string,
    string
  >,
  temporary: MESSAGING_PROTOCOL.temporary,
  transfers: {
    message: MESSAGING_PROTOCOL.message,
    audit: {
      export: "Audited",
      import: "AuditReceipt",
      to: "board",
      requireRole: "Auditor",
    },
  },
} as const;

export function accepts(owner: string, fact: PolicyFact) {
  if (PROTOCOL.replicated.some((p) => p === fact.predicate)) return true;
  const fixed = PROTOCOL.onlyAt[fact.predicate];
  if (fixed && fixed !== owner) return false;
  const pattern = PROTOCOL.local[fact.predicate];
  return (
    !!pattern &&
    pattern.length === fact.args.length &&
    pattern.every((term, i) => term === "_" || fact.args[i] === (term === "@self" ? owner : term))
  );
}
