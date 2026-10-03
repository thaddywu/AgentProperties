import type { PolicyFact } from "@rakazo/contracts";
import { factKey } from "../datalog.js";
import { DERIVED, REASONING_RULES } from "./policy.js";
import { accepts, PROTOCOL } from "./protocol.js";
import type { RuntimeState } from "./runtime.js";
import { PRINCIPALS } from "./shared.js";
import { runSouffle } from "./souffle.js";

export function localInputs(state: RuntimeState, owner: string) {
  if (!PRINCIPALS.some((p) => p === owner)) throw new Error(`Unknown store: ${owner}`);
  const records = state.stores[owner];
  if (!records) throw new Error(`Missing local store: ${owner}`);
  for (const record of records)
    if (record.owner !== owner || !accepts(owner, record.fact))
      throw new Error(`Misplaced fact in ${owner}: ${record.fact.predicate}`);
  return records.map((r) => r.fact);
}
/** Bind location variables before evaluation, so locality also constrains recursion. */
export function localRules(owner: string) {
  return REASONING_RULES.flatMap((rule) => {
    if (PROTOCOL.onlyAt[rule.head.predicate] && PROTOCOL.onlyAt[rule.head.predicate] !== owner)
      return [];
    const pattern = PROTOCOL.local[rule.head.predicate];
    if (!pattern) return [];
    const bindings = new Map<string, string>();
    for (let i = 0; i < pattern.length; i++) {
      if (pattern[i] === "_") continue;
      const expected = pattern[i] === "@self" ? owner : pattern[i]!;
      const term = rule.head.args[i]!;
      if (/^[A-Z]/.test(term)) bindings.set(term, `c:${expected}`);
      else if (term !== expected) return [];
    }
    const bind = (value: string) => bindings.get(value) ?? value;
    return [
      {
        ...rule,
        head: { ...rule.head, args: rule.head.args.map(bind) },
        body: rule.body.map((b) => ({ ...b, args: b.args.map(bind) })),
        distinct: rule.distinct.map(([a, b]): [string, string] => [bind(a), bind(b)]),
      },
    ];
  });
}
export function localClosure(state: RuntimeState, owner: string) {
  return runSouffle(localInputs(state, owner), localRules(owner));
}
/** Observer union of independently computed stores. Never evaluated as a policy program. */
export function reconstructDebugView(state: RuntimeState) {
  const stores = Object.fromEntries(
    PRINCIPALS.map((owner) => [owner, localClosure(state, owner).facts]),
  );
  const unique = new Map<string, PolicyFact>();
  for (const facts of Object.values(stores))
    for (const fact of facts) unique.set(factKey(fact), fact);
  return { stores, facts: [...unique.values()] };
}
export function derivedAt(state: RuntimeState) {
  const { stores, facts } = reconstructDebugView(state);
  return facts
    .filter((f) => DERIVED.has(f.predicate))
    .map((fact) => ({
      fact,
      owners: Object.entries(stores)
        .filter(([, tuples]) => tuples.some((f) => factKey(f) === factKey(fact)))
        .map(([owner]) => owner),
      rule: "Soufflé · local",
    }));
}
