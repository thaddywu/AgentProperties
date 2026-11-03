import type { PolicyFact, Rule } from "./datalog.js";
import { evaluateDatalog, factKey } from "./datalog.js";
import { decode, encodeFact, limits, validateAndStratify } from "./query.js";

const variableTerm = (term: string) => /^[A-Z]/.test(term) || term.startsWith("c:");

export type FiniteSchema = Readonly<Record<string, { kind: string; args: readonly string[] }>>;
export type InputLiteral = { fact: PolicyFact; present: boolean };
export type FiniteInputSpace = {
  required: PolicyFact[];
  optional: PolicyFact[];
  /** Conjunction of clauses; each clause is a disjunction of EDB-presence literals. */
  constraints?: InputLiteral[][];
};
export type FiniteComparison = {
  schema: FiniteSchema;
  reference: Rule[];
  translated: Rule[];
  observables: string[];
  space: FiniteInputSpace;
};
export class ComparisonLimit extends Error {}

/** Parsed rules only. Every non-catalog EDB tuple is false in this finite search. */
export function prepareComparison(input: FiniteComparison): FiniteComparison {
  const comparison = structuredClone(input);
  const { schema, space, observables } = comparison;
  if (
    !observables.length ||
    new Set(observables).size !== observables.length ||
    observables.some((p) => !Object.hasOwn(schema, p))
  )
    throw new Error("Declare distinct known observable predicates.");
  if (space.optional.length > 128)
    throw new ComparisonLimit("At most 128 optional input tuples are supported.");
  const catalog = new Set<string>();
  for (const f of [...space.required, ...space.optional]) {
    const definition = schema[f.predicate];
    if (
      definition?.kind !== "input" ||
      definition.args.length !== f.args.length ||
      f.args.some((a) => typeof a !== "string" || a.length > 1024)
    )
      throw new Error("The input catalog must contain declared ground EDB tuples.");
    if (catalog.has(factKey(f)))
      throw new Error("Required and optional input tuples must be distinct.");
    catalog.add(factKey(f));
  }
  for (const clause of space.constraints ?? [])
    for (const literal of clause)
      if (typeof literal.present !== "boolean" || !catalog.has(factKey(literal.fact)))
        throw new Error("Constraints must reference catalog EDB tuples.");
  for (const rules of [comparison.reference, comparison.translated]) {
    for (const rule of rules) {
      if (schema[rule.head.predicate]?.kind !== "derived")
        throw new Error("Rules cannot write EDB.");
      for (const atom of [rule.head, ...rule.body]) {
        if (schema[atom.predicate]?.args.length !== atom.args.length)
          throw new Error("Unknown predicate or arity in comparison.");
        if (atom.args.some((term) => !variableTerm(term)))
          throw new Error("Comparison rules must use parsed/encoded constants.");
      }
      if (rule.distinct.flat().some((term) => !variableTerm(term)))
        throw new Error("Comparison rules must use parsed/encoded constants.");
    }
    validateAndStratify([], rules);
  }
  return comparison;
}

export function admits(space: FiniteInputSpace, inputs: PolicyFact[]) {
  const present = new Set(inputs.map(factKey));
  return (space.constraints ?? []).every((clause) =>
    clause.some((literal) => present.has(factKey(literal.fact)) === literal.present),
  );
}
export function observe(inputs: PolicyFact[], rules: Rule[], observables: readonly string[]) {
  const selected = new Set(observables);
  return evaluateDatalog(inputs.map(encodeFact), rules, limits)
    .facts.filter((fact) => selected.has(fact.predicate))
    .map((fact) => ({ ...fact, args: fact.args.map(decode) }))
    .sort((a, b) => (factKey(a) < factKey(b) ? -1 : factKey(a) > factKey(b) ? 1 : 0));
}
export function replay(comparison: FiniteComparison, inputs: PolicyFact[]) {
  const reference = observe(inputs, comparison.reference, comparison.observables);
  const translated = observe(inputs, comparison.translated, comparison.observables);
  const left = new Set(reference.map(factKey)),
    right = new Set(translated.map(factKey));
  return {
    different: JSON.stringify(reference) !== JSON.stringify(translated),
    reference,
    translated,
    referenceOnly: reference.filter((f) => !right.has(factKey(f))),
    translatedOnly: translated.filter((f) => !left.has(factKey(f))),
  };
}

/** Deletion-minimal among optional tuples under the declared constraints, with an explicit budget. */
export function shrinkCounterexample(
  comparison: FiniteComparison,
  original: PolicyFact[],
  maxChecks = 128,
) {
  if (!admits(comparison.space, original) || !replay(comparison, original).different)
    throw new Error("A counterexample must satisfy the domain and replay a difference.");
  const required = new Set(comparison.space.required.map(factKey));
  let inputs = structuredClone(original),
    checks = 0,
    changed = true;
  while (changed && checks < maxChecks) {
    changed = false;
    for (const fact of [...inputs]) {
      if (required.has(factKey(fact))) continue;
      if (checks >= maxChecks) break;
      const candidate = inputs.filter((f) => factKey(f) !== factKey(fact));
      checks++;
      if (admits(comparison.space, candidate) && replay(comparison, candidate).different) {
        inputs = candidate;
        changed = true;
      }
    }
  }
  return {
    inputs,
    ...replay(comparison, inputs),
    replayVerified: true,
    shrink: { checks, deletionMinimal: !changed && checks < maxChecks },
  };
}

/** Deterministic EDB testing. Exhaustive completion can establish equality only in this catalog. */
export function testFiniteEquivalence(
  input: FiniteComparison,
  options: {
    mode: "exhaustive" | "sampled";
    seed?: number;
    cases?: number;
  },
) {
  const comparison = prepareComparison(input);
  const count = options.cases ?? 1024;
  if (!Number.isSafeInteger(count) || count < 1 || count > 1_000_000)
    throw new Error("Choose 1–1,000,000 input cases.");
  let state = options.seed ?? 239;
  if (!Number.isInteger(state) || state < 0 || state > 0xffffffff)
    throw new Error("Seed must be an unsigned 32-bit integer.");
  const seed = state;
  const width = comparison.space.optional.length,
    total = 1n << BigInt(width);
  let examined = 0,
    admitted = 0;
  const seen = new Set<string>();
  const candidateMask = (i: number) => {
    if (options.mode === "exhaustive") return BigInt(i);
    if (i === 0) return 0n;
    if (i === 1) return total - 1n;
    if (i - 2 < width) return 1n << BigInt(i - 2);
    let mask = 0n;
    for (let j = 0; j < width; j++) {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      if (state >>> 31) mask |= 1n << BigInt(j);
    }
    return mask;
  };
  for (let i = 0; examined < count && BigInt(seen.size) < total && i < count * 20; i++) {
    const mask = candidateMask(i),
      key = mask.toString();
    if (seen.has(key)) continue;
    seen.add(key);
    examined++;
    const inputs = [
      ...comparison.space.required,
      ...comparison.space.optional.filter((_, j) => mask & (1n << BigInt(j))),
    ];
    if (!admits(comparison.space, inputs)) continue;
    admitted++;
    if (replay(comparison, inputs).different)
      return {
        status: "different" as const,
        method: options.mode,
        seed,
        examined,
        admitted,
        totalAssignments: total.toString(),
        counterexample: shrinkCounterexample(comparison, inputs),
      };
  }
  const complete = BigInt(examined) === total;
  return {
    status:
      complete && options.mode === "exhaustive"
        ? admitted
          ? ("equivalent_within_bound" as const)
          : ("empty_domain" as const)
        : admitted
          ? ("tested_no_difference" as const)
          : ("inconclusive" as const),
    method: options.mode,
    seed,
    examined,
    admitted,
    complete,
    totalAssignments: total.toString(),
  };
}
