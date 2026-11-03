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
    Covered: ["_"],
  } as Record<string, string[]>,
  onlyAt: { TrustedSource: "board" } as Record<string, string>,
  observer: ["Finished"],
  temporary: MESSAGING_PROTOCOL.temporary,
  transfers: { message: MESSAGING_PROTOCOL.message },
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

/** App-only additions, projected from the executable protocol for display. */
export const NOVA_PROTOCOL = {
  replicated: PROTOCOL.replicated.filter(
    (predicate) => !MESSAGING_PROTOCOL.replicated.some((base) => base === predicate),
  ),
  local: Object.fromEntries(
    Object.entries(PROTOCOL.local).filter(
      ([predicate]) => !Object.hasOwn(MESSAGING_PROTOCOL.local, predicate),
    ),
  ),
  onlyAt: PROTOCOL.onlyAt,
  observer: PROTOCOL.observer,
  transfers: {},
};
