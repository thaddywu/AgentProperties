import type { PolicyFact, Rule } from "./datalog.js";

export type PredicateDefinition = {
  args: string[];
  kind: "input" | "derived";
  source: "runtime" | "transport" | "trusted source" | "config" | "inference";
};

/** Vocabulary supplied by the messaging/IFC/capability foundation. Values belong to the app. */
export const MESSAGING_PREDICATES: Record<string, PredicateDefinition> = {
  Sender: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  Receiver: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  Received: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  Incoming: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  Before: { args: ["EarlierMessage", "LaterMessage"], kind: "input", source: "runtime" },
  TrustedSource: { args: ["Message", "Tag"], kind: "input", source: "trusted source" },
  TransportTag: { args: ["Message", "Tag"], kind: "input", source: "transport" },
  HasCap: { args: ["Principal", "Capability"], kind: "input", source: "config" },
  Requires: { args: ["Tag", "Capability"], kind: "input", source: "config" },
  TagGroup: { args: ["Tag", "Group"], kind: "input", source: "config" },
  DependsOn: { args: ["OutputMessage", "InputMessage"], kind: "derived", source: "inference" },
  Propagated: { args: ["Message", "Tag"], kind: "derived", source: "inference" },
  Knows: { args: ["Principal", "Tag"], kind: "derived", source: "inference" },
  DenyReceive: { args: ["Principal", "Message"], kind: "derived", source: "inference" },
};

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const rule = (id: string, head: PolicyFact, body: Rule["body"], stratum = 0): Rule => ({
  id,
  head,
  body,
  distinct: [],
  stratum,
});

/** Fixed foundation rules. No principal names, audit semantics or exposure threshold. */
export const MESSAGING_RULES = {
  "trusted-label": rule("trusted-label", f("Propagated", "M", "Tag"), [
    f("TrustedSource", "M", "Tag"),
  ]),
  "message-label": rule("message-label", f("Propagated", "M", "Tag"), [
    f("TransportTag", "M", "Tag"),
  ]),
  "runtime-dependency": rule("runtime-dependency", f("DependsOn", "Mout", "Min"), [
    f("Receiver", "P", "Min"),
    f("Sender", "P", "Mout"),
    f("Before", "Min", "Mout"),
  ]),
  "label-propagation": rule("label-propagation", f("Propagated", "Mout", "Tag"), [
    f("DependsOn", "Mout", "Min"),
    f("Propagated", "Min", "Tag"),
  ]),
  knowledge: rule("knowledge", f("Knows", "P", "Tag"), [
    f("Received", "P", "M"),
    f("Propagated", "M", "Tag"),
  ]),
  capability: rule(
    "capability",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Propagated", "M", "Tag"),
      f("Requires", "Tag", "Cap"),
      { ...f("HasCap", "P", "Cap"), negative: true },
    ],
    1,
  ),
} satisfies Record<string, Rule>;
