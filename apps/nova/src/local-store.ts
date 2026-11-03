import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { DERIVED } from "./policy.js";
import { accepts, PROTOCOL } from "./protocol.js";
import type { RuntimeState } from "./runtime.js";
import { PRINCIPALS } from "./shared.js";
import { rulesFor } from "./translated-policy.js";

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
export function localRules(owner: string, state: Pick<RuntimeState, "policy"> = {}) {
  return rulesFor(state).flatMap((rule) => {
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
      else if ((term.startsWith("c:") ? term.slice(2) : term) !== expected) return [];
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
  return runSouffle(localInputs(state, owner), localRules(owner, state));
}
/** Only observer outputs may be computed across stores; local enforcement never reads them. */
export function observerRules(state: Pick<RuntimeState, "policy"> = {}) {
  return rulesFor(state).filter((rule) => PROTOCOL.observer.some((p) => p === rule.head.predicate));
}
/** Union local closures, then evaluate only observer rules. Never rerun local gate rules here. */
export function reconstructDebugView(state: RuntimeState) {
  const stores = Object.fromEntries(
    PRINCIPALS.map((owner) => [owner, localClosure(state, owner).facts]),
  );
  const unique = new Map<string, PolicyFact>();
  for (const facts of Object.values(stores))
    for (const fact of facts) unique.set(factKey(fact), fact);
  const localFacts = [...unique.values()];
  const observer = runSouffle(localFacts, observerRules(state)).facts.filter((fact) =>
    PROTOCOL.observer.some((p) => p === fact.predicate),
  );
  for (const fact of observer) unique.set(factKey(fact), fact);
  return { stores, localFacts, observer, facts: [...unique.values()] };
}
export function derivedAt(state: RuntimeState) {
  const { stores, facts } = reconstructDebugView(state);
  return facts
    .filter((f) => DERIVED.has(f.predicate))
    .map((fact) => ({
      fact,
      owners: PROTOCOL.observer.some((p) => p === fact.predicate)
        ? ["observer"]
        : Object.entries(stores)
            .filter(([, tuples]) => tuples.some((f) => factKey(f) === factKey(fact)))
            .map(([owner]) => owner),
      rule: PROTOCOL.observer.some((p) => p === fact.predicate)
        ? "Soufflé · global query"
        : "Soufflé · local",
    }));
}
