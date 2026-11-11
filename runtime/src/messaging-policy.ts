import type { PolicyFact, Rule } from "./datalog.js";

export type PredicateDefinition = {
  args: string[];
  kind: "input" | "derived";
  source: "runtime" | "transport" | "trusted source" | "config" | "inference";
};

/** Vocabulary supplied by the messaging/IFC/capability foundation. Values belong to the app. */
export const MESSAGING_PREDICATES: Record<string, PredicateDefinition> = {
  Sender: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  Received: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  Incoming: { args: ["Principal", "Message"], kind: "input", source: "runtime" },
  ReceivedBeforeSend: {
    args: ["EarlierMessage", "LaterMessage"],
    kind: "input",
    source: "runtime",
  },
  TrustedSource: { args: ["Message", "Tag"], kind: "input", source: "trusted source" },
  TransportTag: { args: ["Message", "Tag"], kind: "input", source: "transport" },
  HasCap: { args: ["Principal", "Capability"], kind: "input", source: "config" },
  Requires: { args: ["Tag", "Capability"], kind: "input", source: "config" },
  TagGroup: { args: ["Tag", "Group"], kind: "input", source: "config" },
  MayDependOn: { args: ["OutputMessage", "InputMessage"], kind: "derived", source: "inference" },
  MessageTag: { args: ["Message", "Tag"], kind: "derived", source: "inference" },
  HasReceivedTag: { args: ["Principal", "Tag"], kind: "derived", source: "inference" },
  Deny: { args: ["Request", "Reason"], kind: "derived", source: "inference" },
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
  "trusted-label": rule("trusted-label", f("MessageTag", "M", "Tag"), [
    f("TrustedSource", "M", "Tag"),
  ]),
  "message-label": rule("message-label", f("MessageTag", "M", "Tag"), [
    f("TransportTag", "M", "Tag"),
  ]),
  "runtime-dependency": rule("runtime-dependency", f("MayDependOn", "Mout", "Min"), [
    f("Received", "P", "Min"),
    f("Sender", "P", "Mout"),
    f("ReceivedBeforeSend", "Min", "Mout"),
  ]),
  "label-propagation": rule("label-propagation", f("MessageTag", "Mout", "Tag"), [
    f("MayDependOn", "Mout", "Min"),
    f("MessageTag", "Min", "Tag"),
  ]),
  "received-tag": rule("received-tag", f("HasReceivedTag", "P", "Tag"), [
    f("Received", "P", "M"),
    f("MessageTag", "M", "Tag"),
  ]),
  capability: rule(
    "capability",
    f("Deny", "M", "message_policy"),
    [
      f("Incoming", "P", "M"),
      f("MessageTag", "M", "Tag"),
      f("Requires", "Tag", "Cap"),
      { ...f("HasCap", "P", "Cap"), negative: true },
    ],
    1,
  ),
} satisfies Record<string, Rule>;
