import type { PolicyFact } from "@rakazo/contracts";

export type Atom = PolicyFact & { negative?: boolean };
export type Rule = {
  id: string;
  head: PolicyFact;
  body: Atom[];
  distinct: [string, string][];
  stratum: number;
};
export type Proof = { rule: string; premises: PolicyFact[] };
export const factKey = (fact: PolicyFact) => JSON.stringify([fact.predicate, ...fact.args]);
const variable = (term: string) => /^[A-Z]/.test(term);
const resolve = (term: string, bindings: Record<string, string>) =>
  variable(term) ? bindings[term] : term;

/** Finite, function-free stratified Datalog. No user text is executable policy. */
export function evaluateDatalog(input: PolicyFact[], rules: Rule[]) {
  const facts = new Map(input.map((fact) => [factKey(fact), fact]));
  const proofs = new Map<string, Proof>();
  for (const stratum of [...new Set(rules.map((rule) => rule.stratum))].sort((a, b) => a - b)) {
    let changed = true;
    while (changed) {
      changed = false;
      for (const rule of rules.filter((item) => item.stratum === stratum)) {
        let matches: { bindings: Record<string, string>; premises: PolicyFact[] }[] = [
          { bindings: {}, premises: [] },
        ];
        for (const atom of rule.body) {
          const candidates = [...facts.values()].filter(
            (fact) => fact.predicate === atom.predicate && fact.args.length === atom.args.length,
          );
          matches = matches.flatMap((match) => {
            if (atom.negative) {
              const terms = atom.args.map((term) => resolve(term, match.bindings));
              if (terms.some((term) => term === undefined))
                throw new Error(`Unsafe negative atom in ${rule.id}`);
              return candidates.some((fact) => fact.args.every((term, i) => term === terms[i]))
                ? []
                : [match];
            }
            return candidates.flatMap((fact) => {
              const bindings = { ...match.bindings };
              for (let i = 0; i < atom.args.length; i++) {
                const term = atom.args[i]!;
                const expected = resolve(term, bindings);
                if (expected !== undefined && expected !== fact.args[i]) return [];
                if (variable(term)) bindings[term] = fact.args[i]!;
              }
              return [{ bindings, premises: [...match.premises, fact] }];
            });
          });
        }
        for (const match of matches) {
          if (
            !rule.distinct.every(([a, b]) => {
              const left = resolve(a, match.bindings),
                right = resolve(b, match.bindings);
              if (left === undefined || right === undefined)
                throw new Error(`Unsafe comparison in ${rule.id}`);
              return left !== right;
            })
          )
            continue;
          const args = rule.head.args.map((term) => {
            const value = resolve(term, match.bindings);
            if (value === undefined) throw new Error(`Unsafe head in ${rule.id}`);
            return value;
          });
          const fact = { predicate: rule.head.predicate, args };
          const key = factKey(fact);
          if (!facts.has(key)) {
            facts.set(key, fact);
            proofs.set(key, { rule: rule.id, premises: match.premises });
            changed = true;
          }
        }
      }
    }
  }
  return { facts: [...facts.values()], proofs };
}
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
export const formatFact = (fact: PolicyFact) => `${fact.predicate}(${fact.args.join(", ")})`;
// Displayed rules are rendered from the actual evaluated AST, never a second implementation.
export const APP2_DATALOG = APP2_RULES.map(
  (rule) =>
    `// ${rule.id}\n${formatFact(rule.head)} :-\n  ${[...rule.body.map((part) => `${part.negative ? "not " : ""}${formatFact(part)}`), ...rule.distinct.map(([a, b]) => `${a} != ${b}`)].join(",\n  ")}.`,
).join("\n\n");
