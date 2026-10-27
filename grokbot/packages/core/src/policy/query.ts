import type { PolicyFact, PolicyStores } from "@rakazo/contracts";
import {
  decode,
  encodeFact,
  encodeRule,
  limits,
  parseProgram,
  validateAndStratify,
} from "@rakazo/policy-runtime/query";
import { APP2_RULES, evaluateDatalog, factKey } from "./datalog.js";

export { parseGroundFacts, parseProgram, queryDatalog } from "@rakazo/policy-runtime/query";

const constant = (value: string) => `c:${value}`;

export function queryPolicyStores(stores: PolicyStores, scope: string, source: string) {
  const parsed = parseProgram(source);
  const global = scope === "global";
  if (!global && !Object.hasOwn(stores, scope)) throw new Error("Unknown principal.");
  const selected = global
    ? Object.entries(stores)
    : Object.entries(stores).filter(([id]) => id === scope);
  const facts = new Map<string, PolicyFact>();
  for (const [owner, store] of selected) {
    // Policy closure is computed locally, never by combining principals' knowledge.
    const closed = evaluateDatalog(
      store.facts.map(encodeFact),
      APP2_RULES.map(encodeRule),
      limits,
    ).facts;
    for (const f of closed) {
      facts.set(factKey(f), f);
      const owned = { predicate: `Store_${f.predicate}`, args: [constant(owner), ...f.args] };
      facts.set(factKey(owned), owned);
    }
  }
  const input = [...facts.values(), ...parsed.facts];
  const rules = [...APP2_RULES.map(encodeRule), ...parsed.rules];
  // Global includes local policy results; only explicit user rules combine stores.
  const active = global ? parsed.rules : rules;
  validateAndStratify(input, active);
  const result = evaluateDatalog(input, active, limits);
  return {
    columns: parsed.columns,
    rows: result.facts.filter((f) => f.predicate === "QueryResult").map((f) => f.args.map(decode)),
  };
}
