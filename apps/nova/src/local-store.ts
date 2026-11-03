import { factKey } from "@rakazo/policy-runtime/datalog";
import { bindLocalRules, distributedClosure } from "@rakazo/policy-runtime/distributed";
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
  return bindLocalRules(PROTOCOL, rulesFor(state), owner);
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
  return distributedClosure(PROTOCOL, rulesFor(state), PRINCIPALS, (owner) =>
    localInputs(state, owner),
  );
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
