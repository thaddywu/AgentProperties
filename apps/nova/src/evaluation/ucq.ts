import type { PolicyFact, Rule } from "@rakazo/policy-runtime/datalog";
import { evaluateDatalog, factKey } from "@rakazo/policy-runtime/datalog";
import { decode, encodeFact, limits, validateAndStratify } from "@rakazo/policy-runtime/query";

const variable = (term: string) => /^[A-Z]/.test(term);

/** Exact containment for flat positive relational UCQs, under set semantics and no constraints. */
export function compareUcq(reference: Rule[], translated: Rule[], output: string) {
  const scope =
    "All finite instances of the declared leaf relations, with no integrity constraints. Parsed flat positive UCQ only; not the complete recursive Nova program.";
  const programs = [structuredClone(reference), structuredClone(translated)];
  if (
    programs.some((rules) =>
      rules.some(
        (r) =>
          r.head.predicate !== output ||
          r.distinct.length ||
          r.body.some((a) => a.negative || a.predicate === output),
      ),
    )
  )
    return {
      status: "unsupported" as const,
      scope,
      reason:
        "Requires only one output predicate, positive relational bodies and no recursion, negation or comparisons.",
    };
  const arities = new Map<string, number>();
  for (const rules of programs) {
    validateAndStratify([], rules);
    for (const r of rules)
      for (const a of [r.head, ...r.body]) {
        if (arities.has(a.predicate) && arities.get(a.predicate) !== a.args.length)
          throw new Error("UCQ schema arity mismatch.");
        arities.set(a.predicate, a.args.length);
      }
  }
  const constants = new Set(
    programs
      .flat(2)
      .flatMap((r) =>
        [r.head, ...r.body].flatMap((a) => a.args.filter((t) => !variable(t)).map(decode)),
      ),
  );
  const containment = (left: Rule[], right: Rule[]) => {
    for (const branch of [...left].sort((a, b) => a.body.length - b.body.length)) {
      const bindings = new Map<string, string>();
      let fresh = 0;
      const ground = (term: string) => {
        if (!variable(term)) return decode(term);
        if (!bindings.has(term)) {
          let value: string;
          do {
            value = `cq_fresh_${fresh++}`;
          } while (constants.has(value));
          bindings.set(term, value);
        }
        return bindings.get(term)!;
      };
      const inputs: PolicyFact[] = branch.body.map((a) => ({
        predicate: a.predicate,
        args: a.args.map(ground),
      }));
      const answer = { predicate: output, args: branch.head.args.map(ground) };
      const result = evaluateDatalog(inputs.map(encodeFact), right, limits);
      if (!result.facts.some((f) => factKey(f) === factKey(encodeFact(answer))))
        return { contained: false, counterexample: { inputs, answer } };
    }
    return { contained: true };
  };
  const forward = containment(programs[0]!, programs[1]!);
  const backward = containment(programs[1]!, programs[0]!);
  return {
    status:
      forward.contained && backward.contained ? ("equivalent" as const) : ("different" as const),
    scope,
    referenceContainedInTranslated: forward,
    translatedContainedInReference: backward,
  };
}
