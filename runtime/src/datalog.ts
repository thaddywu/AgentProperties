export type PolicyFact = { predicate: string; args: string[] };

export type Atom = PolicyFact & { negative?: boolean };
export type Rule = {
  id: string;
  head: PolicyFact;
  body: Atom[];
  distinct: [string, string][];
  stratum: number;
};
export type Proof = {
  rule: string;
  premises: PolicyFact[];
  checks?: { kind: "absence" | "comparison"; text: string }[];
};
export const factKey = (fact: PolicyFact) => JSON.stringify([fact.predicate, ...fact.args]);
const variable = (term: string) => /^[A-Z]/.test(term);
const resolve = (term: string, bindings: Record<string, string>) =>
  variable(term) ? bindings[term] : term;

/** Finite, function-free stratified Datalog. No user text is executable policy. */
export function evaluateDatalog(
  input: PolicyFact[],
  rules: Rule[],
  limits?: { operations: number; facts: number },
) {
  let operations = 0;
  const tick = () => {
    if (limits && (++operations > limits.operations || facts.size > limits.facts))
      throw new Error("Query limit exceeded. Narrow the query or reduce the program.");
  };
  const facts = new Map(input.map((fact) => [factKey(fact), fact]));
  const proofs = new Map<string, Proof>();
  for (const stratum of [...new Set(rules.map((rule) => rule.stratum))].sort((a, b) => a - b)) {
    let changed = true;
    while (changed) {
      changed = false;
      for (const rule of rules.filter((item) => item.stratum === stratum)) {
        tick();
        let matches: { bindings: Record<string, string>; premises: PolicyFact[] }[] = [
          { bindings: {}, premises: [] },
        ];
        for (const atom of rule.body) {
          tick();
          const candidates = [...facts.values()].filter((fact) => {
            tick();
            return fact.predicate === atom.predicate && fact.args.length === atom.args.length;
          });
          matches = matches.flatMap((match) => {
            if (atom.negative) {
              const terms = atom.args.map((term) => resolve(term, match.bindings));
              if (terms.some((term) => term === undefined))
                throw new Error(`Unsafe negative atom in ${rule.id}`);
              return candidates.some((fact) => {
                tick();
                return fact.args.every((term, i) => term === terms[i]);
              })
                ? []
                : [match];
            }
            return candidates.flatMap((fact) => {
              tick();
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
            proofs.set(key, {
              rule: rule.id,
              premises: match.premises,
              checks: [
                ...rule.body
                  .filter((a) => a.negative)
                  .map((a) => ({
                    kind: "absence" as const,
                    text: `not ${a.predicate}(${a.args.map((t) => resolve(t, match.bindings)).join(", ")})`,
                  })),
                ...rule.distinct.map(([a, b]) => ({
                  kind: "comparison" as const,
                  text: `${resolve(a, match.bindings)} != ${resolve(b, match.bindings)}`,
                })),
              ],
            });
            changed = true;
          }
        }
      }
    }
  }
  return { facts: [...facts.values()], proofs };
}

export const formatFact = (fact: PolicyFact) => `${fact.predicate}(${fact.args.join(", ")})`;
