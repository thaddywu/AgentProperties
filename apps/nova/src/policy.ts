import type { PolicyFact, Rule } from "@rakazo/policy-runtime/datalog";
import { factKey, formatFact } from "@rakazo/policy-runtime/datalog";
import type { PredicateDefinition } from "@rakazo/policy-runtime/messaging-policy";
import { MESSAGING_PREDICATES, MESSAGING_RULES } from "@rakazo/policy-runtime/messaging-policy";
import { parseGroundFacts } from "@rakazo/policy-runtime/query";
import { runSouffle, souffleProgram } from "@rakazo/policy-runtime/souffle";

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
export const NOVA_PREDICATES: Record<string, PredicateDefinition> = {
  Auditor: { args: ["Principal"], kind: "input", source: "config" },
  AuditGoal: { args: ["Group", "Tag1", "Tag2", "Tag3"], kind: "input", source: "config" },
  Covered: { args: ["Tag"], kind: "derived", source: "inference" },
  Finished: { args: ["Group"], kind: "derived", source: "inference" },
};
export const NOVA_RULES: Rule[] = [
  rule(
    "three-tag-exposure",
    f("DenyReceive", "P", "M"),
    [
      f("Incoming", "P", "M"),
      f("MessageTag", "M", "T3"),
      f("HasReceivedTag", "P", "T1"),
      f("HasReceivedTag", "P", "T2"),
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
      f("MessageTag", "M", "T2"),
      f("MessageTag", "M", "T3"),
      f("HasReceivedTag", "P", "T1"),
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
      f("MessageTag", "M", "T1"),
      f("MessageTag", "M", "T2"),
      f("MessageTag", "M", "T3"),
      f("TagGroup", "T1", "Group"),
      f("TagGroup", "T2", "Group"),
      f("TagGroup", "T3", "Group"),
    ],
    distinct,
    1,
  ),
  rule("coverage", f("Covered", "Tag"), [
    f("Auditor", "A"),
    f("Received", "A", "M"),
    f("MessageTag", "M", "Tag"),
  ]),
  rule("finished", f("Finished", "Group"), [
    f("AuditGoal", "Group", "T1", "T2", "T3"),
    f("Covered", "T1"),
    f("Covered", "T2"),
    f("Covered", "T3"),
  ]),
];
// Local foundation and application rules; Finished is evaluated only by the observer.
export const REASONING_RULES: Rule[] = [
  MESSAGING_RULES["trusted-label"],
  MESSAGING_RULES["message-label"],
  MESSAGING_RULES["runtime-dependency"],
  MESSAGING_RULES["label-propagation"],
  MESSAGING_RULES["received-tag"],
  MESSAGING_RULES.capability,
  ...NOVA_RULES,
];
export const RULE_TEXT = souffleProgram([], REASONING_RULES);
export { CONFIG } from "./config.js";
export const PREDICATES = { ...MESSAGING_PREDICATES, ...NOVA_PREDICATES };
export const INPUT_ARITIES: Record<string, number> = Object.fromEntries(
  Object.entries(PREDICATES)
    .filter(([, schema]) => schema.kind === "input")
    .map(([name, schema]) => [name, schema.args.length]),
);
export const POLICY_LAYERS = [
  {
    id: "builtin",
    title: "Built-in",
    predicates: MESSAGING_PREDICATES,
    rules: Object.values(MESSAGING_RULES),
  },
  { id: "nova", title: "Nova reference", predicates: NOVA_PREDICATES, rules: NOVA_RULES },
].map((layer) => ({
  id: layer.id,
  title: layer.title,
  predicates: Object.entries(layer.predicates).map(([name, schema]) => ({ name, ...schema })),
  rules: layer.rules.map((rule) => ({
    id: rule.id,
    text: souffleProgram([], [rule])
      .split("\n")
      .filter((line) => !line.startsWith(".") && !line.startsWith("//"))
      .join("\n"),
  })),
}));
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
