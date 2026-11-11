import type { Atom, PolicyFact, Rule } from "./datalog.js";
import { LIFECYCLE_PREDICATES } from "./lifecycle.js";
import { MESSAGING_PREDICATES, MESSAGING_RULES } from "./messaging-policy.js";

/** One foundation, with a readable public vocabulary and the existing Nova compatibility profile. */
export const PRIMITIVE_NAMES = {
  Sender: "MessageSender",
  Received: "MessageReceived",
  Incoming: "ReceiveAttempt",
  ReceivedBeforeSend: "ReceivedBeforeSend",
  TrustedSource: "SourceTag",
  TransportTag: "ImportedTag",
  HasCap: "AgentHasCapability",
  Requires: "TagRequiresCapability",
  TagGroup: "TagGroup",
  MayDependOn: "MessageDependsOn",
  MessageTag: "MessageCarries",
  HasReceivedTag: "Knows",
  Deny: "Deny",
} as const;

export function renameFact<T extends PolicyFact>(
  fact: T,
  names: Readonly<Record<string, string>>,
): T {
  return { ...fact, predicate: names[fact.predicate] ?? fact.predicate };
}
export function renameRule(rule: Rule, names: Readonly<Record<string, string>>): Rule {
  return {
    ...rule,
    head: renameFact(rule.head, names),
    body: rule.body.map((atom: Atom) => renameFact(atom, names)),
  };
}
export const PRIMITIVES = {
  ...Object.fromEntries(
    Object.entries(MESSAGING_PREDICATES).map(([name, schema]) => [
      PRIMITIVE_NAMES[name as keyof typeof PRIMITIVE_NAMES],
      schema,
    ]),
  ),
  ...LIFECYCLE_PREDICATES,
};
export const PRIMITIVE_MESSAGING_RULES = Object.values(MESSAGING_RULES).map((rule) =>
  renameRule(rule, PRIMITIVE_NAMES),
);
export const LEGACY_PRIMITIVE_NAMES = Object.fromEntries(
  Object.entries(PRIMITIVE_NAMES).map(([legacy, current]) => [current, legacy]),
);

/** Knows means tracked information after a successful observed receipt, not semantic omniscience. */
export const MESSAGE_ROLES = {
  sender: "MessageSender",
  received: "MessageReceived",
  incoming: "ReceiveAttempt",
  order: "ReceivedBeforeSend",
  source: "SourceTag",
  imported: "ImportedTag",
  carries: "MessageCarries",
  deny: "Deny",
} as const;
