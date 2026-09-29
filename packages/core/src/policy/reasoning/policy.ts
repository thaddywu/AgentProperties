import type { PolicyFact } from "@rakazo/contracts";
import type { Rule } from "../datalog.js";
import { evaluateDatalog, factKey, formatFact } from "../datalog.js";
import { parseGroundFacts } from "../query.js";

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
  ["C1", "C2"],
  ["C1", "C3"],
  ["C2", "C3"],
];
export const REASONING_RULES: Rule[] = [
  rule("trusted-label", f("Carries", "M", "Proj", "Part"), [
    f("TrustedCarry", "M", "Proj", "Part"),
  ]),
  rule("runtime-dependency", f("DependsOn", "Mout", "Min"), [
    f("Receiver", "P", "Min"),
    f("Sender", "P", "Mout"),
    f("Before", "Min", "Mout"),
  ]),
  rule("label-propagation", f("Carries", "Mout", "Proj", "Part"), [
    f("DependsOn", "Mout", "Min"),
    f("Carries", "Min", "Proj", "Part"),
  ]),
  rule("knowledge", f("Knows", "P", "Proj", "Part"), [
    f("Received", "P", "M"),
    f("Carries", "M", "Proj", "Part"),
  ]),
  rule(
    "capability",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Carries", "M", "Proj", "Part"),
      f("Requires", "Proj", "Part", "Cap"),
      { ...f("HasCap", "P", "Cap"), negative: true },
    ],
    [],
    1,
  ),
  rule(
    "three-part-exposure",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Carries", "M", "Proj", "C3"),
      f("Knows", "P", "Proj", "C1"),
      f("Knows", "P", "Proj", "C2"),
    ],
    distinct,
    1,
  ),
  // The TeX's single-part case is above. Cover multi-label messages as well.
  rule(
    "three-part-two-incoming",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Carries", "M", "Proj", "C2"),
      f("Carries", "M", "Proj", "C3"),
      f("Knows", "P", "Proj", "C1"),
    ],
    distinct,
    1,
  ),
  rule(
    "three-part-all-incoming",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("Carries", "M", "Proj", "C1"),
      f("Carries", "M", "Proj", "C2"),
      f("Carries", "M", "Proj", "C3"),
    ],
    distinct,
    1,
  ),
  rule("audit-progress", f("Audited", "Proj", "Part"), [
    f("Auditor", "A"),
    f("Received", "A", "M"),
    f("Carries", "M", "Proj", "Part"),
  ]),
  rule("finished", f("Finished", "Proj"), [
    f("Audited", "Proj", "procurement"),
    f("Audited", "Proj", "facility"),
    f("Audited", "Proj", "hiring"),
  ]),
];
export const RULE_TEXT = REASONING_RULES.map(
  (r) =>
    `% ${r.id}\n${formatFact(r.head)} :- ${[...r.body.map((a) => `${a.negative ? "not " : ""}${formatFact(a)}`), ...r.distinct.map(([a, b]) => `${a} != ${b}`)].join(", ")}.`,
).join("\n\n");
export const CONFIG = [
  f("Auditor", "auditor_a"),
  f("Auditor", "auditor_b"),
  f("HasCap", "auditor_a", "hr_review"),
  f("HasCap", "hr", "hr_review"),
  f("Requires", "nova", "hiring", "hr_review"),
];
export const INPUT_ARITIES: Record<string, number> = {
  Auditor: 1,
  HasCap: 2,
  Requires: 3,
  TrustedCarry: 3,
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
  return evaluateDatalog(input, REASONING_RULES, { operations: 2_000_000, facts: 10_000 });
}
export const contains = (facts: PolicyFact[], target: PolicyFact) =>
  facts.some((fact) => factKey(fact) === factKey(target));
