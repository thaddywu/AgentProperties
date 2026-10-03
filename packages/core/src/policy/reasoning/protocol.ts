import type { PolicyFact } from "@rakazo/contracts";

/** @self binds to the store's principal; _ matches any value.
 * Placement governs actual local engine input/output, not just UI labels.
 * Shared config is explicitly copied into every local store.
 */
export const PROTOCOL = {
  replicated: ["Auditor", "Requires", "TagGroup", "AuditGoal"],
  local: {
    HasCap: ["@self", "_"],
    Sender: ["@self", "_"],
    Receiver: ["@self", "_"],
    Received: ["@self", "_"],
    Incoming: ["@self", "_"],
    TrustedSource: ["_", "_"],
    TransportTag: ["_", "_"],
    Before: ["_", "_"],
    DependsOn: ["_", "_"],
    Propagated: ["_", "_"],
    Knows: ["@self", "_"],
    DenyReceive: ["@self", "_"],
    Audited: ["_"],
    AuditReceipt: ["_", "_"],
    Finished: ["_"],
  } as Record<string, string[]>,
  onlyAt: { TrustedSource: "board", AuditReceipt: "board", Finished: "board" } as Record<
    string,
    string
  >,
  temporary: ["Incoming"],
  transfers: {
    message: {
      export: "Propagated",
      import: "TransportTag",
      messageArgument: 0,
      retain: "on-allow", // present temporarily for the receiver's gate, discard on deny
    },
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
