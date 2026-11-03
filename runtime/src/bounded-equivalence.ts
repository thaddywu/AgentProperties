import type { Atom, PolicyFact, Rule } from "./datalog.js";
import { factKey } from "./datalog.js";
import type { FiniteComparison } from "./finite-domain.js";
import {
  admits,
  ComparisonLimit,
  prepareComparison,
  replay,
  shrinkCounterexample,
} from "./finite-domain.js";
import { encodeFact } from "./query.js";

export type Cnf = { variables: number; clauses: number[][] };
export type SatResult =
  | { status: "sat"; trueVariables: number[] }
  | { status: "unsat" }
  | { status: "unknown"; reason: string };
export type SatSolver = (formula: Cnf) => SatResult;
type Quotas = {
  operations: number;
  facts: number;
  groundRules: number;
  variables: number;
  clauses: number;
  rounds: number;
};
const defaults: Quotas = {
  operations: 2_000_000,
  facts: 5000,
  groundRules: 20_000,
  variables: 300_000,
  clauses: 1_000_000,
  rounds: 5000,
};
const variable = (s: string) => /^[A-Z]/.test(s);
type GroundRule = { head: PolicyFact; positive: string[]; negative: string[]; stratum: number };

class Circuit {
  formula: Cnf = { variables: 1, clauses: [[1]] };
  private cache = new Map<string, number>();
  constructor(private quota: Quotas) {}
  fresh() {
    if (this.formula.variables >= this.quota.variables)
      throw new ComparisonLimit("SAT variable quota exceeded.");
    return ++this.formula.variables;
  }
  clause(literals: number[]) {
    if (this.formula.clauses.length >= this.quota.clauses)
      throw new ComparisonLimit("SAT clause quota exceeded.");
    this.formula.clauses.push(literals);
  }
  combine(kind: "and" | "or", operands: number[]): number {
    const identity = kind === "and" ? 1 : -1;
    const terms = new Set(operands.filter((v) => v !== identity));
    if (terms.has(-identity) || [...terms].some((v) => terms.has(-v))) return -identity;
    const values = [...terms].sort((a, b) => a - b);
    if (!values.length) return identity;
    if (values.length === 1) return values[0]!;
    const key = `${kind}:${values.join(",")}`;
    const existing = this.cache.get(key);
    if (existing) return existing;
    const result = this.fresh();
    this.cache.set(key, result);
    if (kind === "and") {
      for (const value of values) this.clause([-result, value]);
      this.clause([result, ...values.map((v) => -v)]);
    } else {
      for (const value of values) this.clause([result, -value]);
      this.clause([-result, ...values]);
    }
    return result;
  }
}

/** Positive over-approximation only discovers possible groundings; it is not the encoded semantics. */
function ground(inputs: PolicyFact[], rules: Rule[], quota: Quotas) {
  if (inputs.length > quota.facts) throw new ComparisonLimit("Ground fact quota exceeded.");
  const possible = new Map(inputs.map((f) => [factKey(f), f]));
  const instances = new Map<string, GroundRule>();
  let operations = 0,
    changed = true;
  const tick = () => {
    if (++operations > quota.operations)
      throw new ComparisonLimit("Grounding operation quota exceeded.");
  };
  while (changed) {
    changed = false;
    for (const rule of rules) {
      const positive = rule.body.filter((a) => !a.negative);
      const resolve = (term: string, bindings: Map<string, string>) =>
        variable(term) ? bindings.get(term)! : term;
      const instantiate = (atom: Atom, bindings: Map<string, string>) => ({
        predicate: atom.predicate,
        args: atom.args.map((t) => resolve(t, bindings)),
      });
      const visit = (index: number, bindings: Map<string, string>, premises: string[]) => {
        tick();
        if (index < positive.length) {
          const atom = positive[index]!;
          for (const fact of possible.values()) {
            tick();
            if (fact.predicate !== atom.predicate) continue;
            const next = new Map(bindings);
            let matches = true;
            for (let i = 0; i < atom.args.length; i++) {
              const term = atom.args[i]!,
                known = resolve(term, next);
              if (known !== undefined && known !== fact.args[i]) {
                matches = false;
                break;
              }
              if (variable(term)) next.set(term, fact.args[i]!);
            }
            if (matches) visit(index + 1, next, [...premises, factKey(fact)]);
          }
          return;
        }
        if (rule.distinct.some(([a, b]) => resolve(a, bindings) === resolve(b, bindings))) return;
        const head = instantiate(rule.head, bindings);
        const instance = {
          head,
          positive: premises,
          negative: rule.body
            .filter((a) => a.negative)
            .map((a) => factKey(instantiate(a, bindings))),
          stratum: rule.stratum,
        };
        const key = JSON.stringify(instance);
        if (!instances.has(key)) {
          if (instances.size >= quota.groundRules)
            throw new ComparisonLimit("Ground rule quota exceeded.");
          instances.set(key, instance);
        }
        if (!possible.has(factKey(head))) {
          if (possible.size >= quota.facts)
            throw new ComparisonLimit("Ground fact quota exceeded.");
          possible.set(factKey(head), head);
          changed = true;
        }
      };
      visit(0, new Map(), []);
    }
  }
  return { possible, instances: [...instances.values()], operations };
}

export function dimacs(formula: Cnf) {
  return `p cnf ${formula.variables} ${formula.clauses.length}\n${formula.clauses.map((c) => `${c.join(" ")} 0`).join("\n")}\n`;
}
function validModel(formula: Cnf, values: number[]) {
  const truth = new Set(values);
  return (
    values.every((v) => Number.isInteger(v) && v > 0 && v <= formula.variables) &&
    formula.clauses.every((c) => c.some((v) => (v > 0 ? truth.has(v) : !truth.has(-v))))
  );
}

/** SAT searches all subsets of the optional EDB catalog, not only UCQ programs or sampled snapshots. */
export function boundedEquivalence(
  input: FiniteComparison,
  solver: SatSolver,
  options: {
    quotas?: Partial<Quotas>;
    capture?: (
      name: "domain" | "comparison",
      cnf: Cnf,
      inputs: { fact: PolicyFact; variable: number }[],
    ) => void;
  } = {},
) {
  let prepared = false;
  try {
    const comparison = prepareComparison(input),
      quota = { ...defaults, ...options.quotas };
    prepared = true;
    if (Object.values(quota).some((v) => !Number.isSafeInteger(v) || v < 1))
      throw new Error("SAT quotas must be positive finite integers.");
    const circuit = new Circuit(quota),
      inputVariables: { fact: PolicyFact; variable: number }[] = [];
    const inputs = new Map<string, number>();
    for (const fact of comparison.space.required) inputs.set(factKey(encodeFact(fact)), 1);
    for (const fact of comparison.space.optional) {
      const value = circuit.fresh();
      inputs.set(factKey(encodeFact(fact)), value);
      inputVariables.push({ fact, variable: value });
    }
    for (const clause of comparison.space.constraints ?? [])
      circuit.clause(
        clause.map(
          (literal) => inputs.get(factKey(encodeFact(literal.fact)))! * (literal.present ? 1 : -1),
        ),
      );
    if (comparison.space.constraints?.length) {
      options.capture?.(
        "domain",
        structuredClone(circuit.formula),
        structuredClone(inputVariables),
      );
      const domain = solver(circuit.formula);
      if (domain.status === "unknown")
        return { status: "inconclusive" as const, reason: domain.reason };
      if (domain.status === "unsat") return { status: "empty_domain" as const };
      if (!validModel(circuit.formula, domain.trueVariables))
        return { status: "inconclusive" as const, reason: "Invalid domain SAT model." };
    }
    const catalog = [...comparison.space.required, ...comparison.space.optional].map(encodeFact);
    const programs = [comparison.reference, comparison.translated].map((rules) =>
      ground(catalog, rules, quota),
    );
    const stats = programs.map((program) => ({
      groundRules: program.instances.length,
      possibleFacts: program.possible.size,
      groundingOperations: program.operations,
      roundBounds: [] as { stratum: number; rounds: number }[],
    }));
    let encodingOperations = 0;
    const encode = (program: (typeof programs)[number], index: number) => {
      const committed = new Map<string, number>();
      for (const stratum of [...new Set(program.instances.map((r) => r.stratum))].sort(
        (a, b) => a - b,
      )) {
        const rules = program.instances.filter((r) => r.stratum === stratum);
        const heads = [...new Set(rules.map((r) => factKey(r.head)))];
        const bound = heads.length;
        if (bound > quota.rounds)
          throw new ComparisonLimit(
            "Insufficient fixed-point round budget; no equivalence conclusion.",
          );
        stats[index]!.roundBounds.push({ stratum, rounds: bound });
        let previous = new Map(heads.map((key) => [key, -1]));
        for (let round = 0; round < bound; round++) {
          const alternatives = new Map(heads.map((key) => [key, [previous.get(key)!]]));
          for (const rule of rules) {
            if (++encodingOperations > quota.operations)
              throw new ComparisonLimit("SAT encoding operation quota exceeded.");
            const positive = rule.positive.map(
              (key) => inputs.get(key) ?? previous.get(key) ?? committed.get(key) ?? -1,
            );
            const negative = rule.negative.map(
              (key) => -(inputs.get(key) ?? committed.get(key) ?? -1),
            );
            alternatives
              .get(factKey(rule.head))!
              .push(circuit.combine("and", [...positive, ...negative]));
          }
          previous = new Map(
            [...alternatives].map(([key, values]) => [key, circuit.combine("or", values)]),
          );
        }
        for (const [key, value] of previous) committed.set(key, value);
      }
      return committed;
    };
    const left = encode(programs[0]!, 0),
      right = encode(programs[1]!, 1);
    const selected = new Set(comparison.observables),
      outputs = new Set<string>();
    for (const program of programs)
      for (const [key, fact] of program.possible)
        if (selected.has(fact.predicate)) outputs.add(key);
    const differences = [...outputs].map((key) => {
      const a = left.get(key) ?? inputs.get(key) ?? -1,
        b = right.get(key) ?? inputs.get(key) ?? -1;
      return circuit.combine("or", [
        circuit.combine("and", [a, -b]),
        circuit.combine("and", [-a, b]),
      ]);
    });
    circuit.clause([circuit.combine("or", differences)]);
    options.capture?.(
      "comparison",
      structuredClone(circuit.formula),
      structuredClone(inputVariables),
    );
    const result = solver(circuit.formula);
    const bounds = {
      optionalTuples: inputVariables.length,
      assignments: (1n << BigInt(inputVariables.length)).toString(),
      variables: circuit.formula.variables,
      clauses: circuit.formula.clauses.length,
      programs: stats,
      encodingOperations,
    };
    if (result.status === "unknown")
      return { status: "inconclusive" as const, reason: result.reason, bounds };
    if (result.status === "unsat") return { status: "equivalent_within_bound" as const, bounds };
    if (!validModel(circuit.formula, result.trueVariables))
      return { status: "inconclusive" as const, reason: "Invalid comparison SAT model.", bounds };
    const truth = new Set(result.trueVariables);
    const witness = [
      ...comparison.space.required,
      ...inputVariables.filter((v) => truth.has(v.variable)).map((v) => v.fact),
    ];
    if (!admits(comparison.space, witness) || !replay(comparison, witness).different)
      return {
        status: "inconclusive" as const,
        reason: "SAT counterexample did not replay in the Datalog evaluator.",
        bounds,
      };
    return {
      status: "different" as const,
      bounds,
      counterexample: shrinkCounterexample(comparison, witness),
    };
  } catch (error) {
    return {
      status:
        error instanceof ComparisonLimit || prepared
          ? ("inconclusive" as const)
          : ("unsupported" as const),
      reason: error instanceof Error ? error.message : "Comparison failed.",
    };
  }
}
