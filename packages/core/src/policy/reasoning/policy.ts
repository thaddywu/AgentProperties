import type { PolicyFact } from "@rakazo/contracts";
import type { Rule } from "../datalog.js";
import { factKey, formatFact } from "../datalog.js";
import { parseGroundFacts } from "../query.js";
import { runSouffle, souffleProgram } from "./souffle.js";

export const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const rule = (
  id: string,
  head: PolicyFact,
  body: Rule["body"],
  distinct: Rule["distinct"] = [],
  stratum = 0,
): Rule => ({ id, head, body, distinct, stratum });
const distinct: Rule["distinct"] = [
  ["P", "board"],
  ["T1", "T2"],
  ["T1", "T3"],
  ["T2", "T3"],
];
export const REASONING_RULES: Rule[] = [
  rule("trusted-label", f("Propagated", "M", "Tag"), [f("TrustedSource", "M", "Tag")]),
  rule("message-label", f("Propagated", "M", "Tag"), [f("TransportTag", "M", "Tag")]),
  rule("audit-receipt", f("Audited", "Tag"), [f("AuditReceipt", "A", "Tag")]),
  rule("runtime-dependency", f("DependsOn", "Mout", "Min"), [
    f("Receiver", "P", "Min"),
    f("Sender", "P", "Mout"),
    f("Before", "Min", "Mout"),
  ]),
  rule("label-propagation", f("Propagated", "Mout", "Tag"), [
    f("DependsOn", "Mout", "Min"),
    f("Propagated", "Min", "Tag"),
  ]),
  rule("knowledge", f("Knows", "P", "Tag"), [f("Received", "P", "M"), f("Propagated", "M", "Tag")]),
  rule(
    "capability",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Propagated", "M", "Tag"),
      f("Requires", "Tag", "Cap"),
      { ...f("HasCap", "P", "Cap"), negative: true },
    ],
    [],
    1,
  ),
  rule(
    "three-tag-exposure",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Propagated", "M", "T3"),
      f("Knows", "P", "T1"),
      f("Knows", "P", "T2"),
      f("TagGroup", "T1", "Group"),
      f("TagGroup", "T2", "Group"),
      f("TagGroup", "T3", "Group"),
    ],
    distinct,
    1,
  ),
  // The TeX's single-part case is above. Cover multi-label messages as well.
  rule(
    "three-tag-two-incoming",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Propagated", "M", "T2"),
      f("Propagated", "M", "T3"),
      f("Knows", "P", "T1"),
      f("TagGroup", "T1", "Group"),
      f("TagGroup", "T2", "Group"),
      f("TagGroup", "T3", "Group"),
    ],
    distinct,
    1,
  ),
  rule(
    "three-tag-all-incoming",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Propagated", "M", "T1"),
      f("Propagated", "M", "T2"),
      f("Propagated", "M", "T3"),
      f("TagGroup", "T1", "Group"),
      f("TagGroup", "T2", "Group"),
      f("TagGroup", "T3", "Group"),
    ],
    distinct,
    1,
  ),
  rule("audit-progress", f("Audited", "Tag"), [
    f("Auditor", "A"),
    f("Received", "A", "M"),
    f("Propagated", "M", "Tag"),
  ]),
  rule("finished", f("Finished", "Group"), [
    f("AuditGoal", "Group", "T1", "T2", "T3"),
    f("Audited", "T1"),
    f("Audited", "T2"),
    f("Audited", "T3"),
  ]),
];
export const RULE_TEXT = souffleProgram([], REASONING_RULES);
export { CONFIG } from "./config.js";
export const INPUT_ARITIES: Record<string, number> = {
  Auditor: 1,
  TagGroup: 2,
  AuditGoal: 4,
  HasCap: 2,
  Requires: 2,
  TrustedSource: 2,
  TransportTag: 2,
  AuditReceipt: 2,
  Sender: 2,
  Receiver: 2,
  Before: 2,
  Received: 2,
  Incoming: 2,
};
export const DERIVED = new Set(REASONING_RULES.map((r) => r.head.predicate));
export function validateInput(fact: PolicyFact) {
  if (DERIVED.has(fact.predicate))
    throw new Error(`Derived facts are read-only: ${fact.predicate}`);
  if (INPUT_ARITIES[fact.predicate] !== fact.args.length)
    throw new Error(`Unknown input predicate or wrong arity: ${formatFact(fact)}`);
}
export function parseInputs(source: string) {
  const facts = parseGroundFacts(source);
  facts.forEach(validateInput);
  return facts;
}
export function parseTarget(source: string) {
  const facts = parseGroundFacts(source.trim().replace(/\.?$/, "."));
  if (facts.length !== 1) throw new Error("Enter exactly one ground fact.");
  const target = facts[0]!;
  const sample = REASONING_RULES.flatMap((r) => [r.head, ...r.body]).find(
    (a) => a.predicate === target.predicate,
  );
  if (!sample || sample.args.length !== target.args.length)
    throw new Error("Unknown query predicate or wrong arity.");
  return target;
}
export function evaluate(input: PolicyFact[]) {
  input.forEach(validateInput);
  return runSouffle(input, REASONING_RULES);
}
export const contains = (facts: PolicyFact[], target: PolicyFact) =>
  facts.some((fact) => factKey(fact) === factKey(target));
