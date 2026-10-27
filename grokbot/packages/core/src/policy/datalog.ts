import type { Atom, Rule } from "@rakazo/policy-runtime/datalog";
import { formatFact } from "@rakazo/policy-runtime/datalog";

export type { Atom, Proof, Rule } from "@rakazo/policy-runtime/datalog";
export { evaluateDatalog, factKey, formatFact } from "@rakazo/policy-runtime/datalog";

const atom = (predicate: string, ...args: string[]): Atom => ({ predicate, args });
const distinct: [string, string][] = [
  ["A", "board"],
  ["C1", "C2"],
  ["C1", "C3"],
  ["C2", "C3"],
];
export const APP2_RULES: Rule[] = [
  {
    id: "R1",
    stratum: 0,
    head: atom("Carries", "Y", "P", "C"),
    body: [atom("DerivedFrom", "Y", "X"), atom("Carries", "X", "P", "C")],
    distinct: [],
  },
  {
    id: "R2",
    stratum: 0,
    head: atom("Knows", "A", "P", "C"),
    body: [atom("Received", "A", "M"), atom("Carries", "M", "P", "C")],
    distinct: [],
  },
  {
    id: "New",
    stratum: 1,
    head: atom("New", "A", "M", "P", "C"),
    body: [
      atom("Incoming", "A", "M"),
      atom("Carries", "M", "P", "C"),
      { ...atom("Knows", "A", "P", "C"), negative: true },
    ],
    distinct: [],
  },
  {
    id: "R3a",
    stratum: 2,
    head: atom("Deny", "A", "M", "r3a"),
    body: [
      atom("New", "A", "M", "P", "C1"),
      atom("New", "A", "M", "P", "C2"),
      atom("New", "A", "M", "P", "C3"),
    ],
    distinct,
  },
  {
    id: "R3b",
    stratum: 2,
    head: atom("Deny", "A", "M", "r3b"),
    body: [
      atom("New", "A", "M", "P", "C1"),
      atom("New", "A", "M", "P", "C2"),
      atom("Knows", "A", "P", "C3"),
    ],
    distinct,
  },
  {
    id: "R3c",
    stratum: 2,
    head: atom("Deny", "A", "M", "r3c"),
    body: [
      atom("New", "A", "M", "P", "C1"),
      atom("Knows", "A", "P", "C2"),
      atom("Knows", "A", "P", "C3"),
    ],
    distinct,
  },
];
// Displayed rules are rendered from the actual evaluated AST, never a second implementation.
export const APP2_DATALOG = APP2_RULES.map(
  (rule) =>
    `// ${rule.id}\n${formatFact(rule.head)} :-\n  ${[...rule.body.map((part) => `${part.negative ? "not " : ""}${formatFact(part)}`), ...rule.distinct.map(([a, b]) => `${a} != ${b}`)].join(",\n  ")}.`,
).join("\n\n");
