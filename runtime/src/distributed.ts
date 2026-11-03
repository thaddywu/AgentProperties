import type { PolicyFact, Rule } from "./datalog.js";
import { factKey } from "./datalog.js";
import { decode } from "./query.js";
import { runSouffle } from "./souffle.js";

export type PlacementProtocol = {
  replicated: readonly string[];
  local: Readonly<Record<string, readonly string[]>>;
  onlyAt: Readonly<Record<string, string>>;
  observer: readonly string[];
  ruleLocations?: Readonly<Record<string, readonly string[]>>;
};
export function acceptsFact(protocol: PlacementProtocol, owner: string, fact: PolicyFact) {
  if (protocol.replicated.includes(fact.predicate)) return true;
  if (protocol.onlyAt[fact.predicate] && protocol.onlyAt[fact.predicate] !== owner) return false;
  const pattern = protocol.local[fact.predicate];
  return (
    !!pattern &&
    pattern.length === fact.args.length &&
    pattern.every((term, i) => term === "_" || fact.args[i] === (term === "@self" ? owner : term))
  );
}
/** The same placement/binding implementation serves every application profile. */
export function bindLocalRules(protocol: PlacementProtocol, rules: Rule[], owner: string) {
  return rules.flatMap((rule) => {
    if (protocol.ruleLocations?.[rule.id] && !protocol.ruleLocations[rule.id]!.includes(owner))
      return [];
    if (protocol.onlyAt[rule.head.predicate] && protocol.onlyAt[rule.head.predicate] !== owner)
      return [];
    const pattern = protocol.local[rule.head.predicate];
    if (!pattern) return [];
    const bindings = new Map<string, string>();
    for (let i = 0; i < pattern.length; i++) {
      if (pattern[i] === "_") continue;
      const expected = pattern[i] === "@self" ? owner : pattern[i]!;
      const term = rule.head.args[i]!;
      if (/^[A-Z]/.test(term)) bindings.set(term, `c:${expected}`);
      else if (decode(term) !== expected) return [];
    }
    const bind = (term: string) => bindings.get(term) ?? term;
    return [
      {
        ...rule,
        head: { ...rule.head, args: rule.head.args.map(bind) },
        body: rule.body.map((atom) => ({ ...atom, args: atom.args.map(bind) })),
        distinct: rule.distinct.map(([a, b]): [string, string] => [bind(a), bind(b)]),
      },
    ];
  });
}
/** Static locality checks are separate from a finite behavior comparison. */
export function validateRuleLocality(protocol: PlacementProtocol, rules: Rule[]) {
  for (const rule of rules) {
    if (protocol.observer.includes(rule.head.predicate)) continue;
    const localTerms = new Set<string>();
    const constants = new Set<string>();
    const inspect = (atom: PolicyFact) => {
      const pattern = protocol.local[atom.predicate];
      if (protocol.onlyAt[atom.predicate]) constants.add(protocol.onlyAt[atom.predicate]!);
      pattern?.forEach((slot, i) => {
        if (slot !== "@self") return;
        const term = atom.args[i]!;
        if (/^[A-Z]/.test(term)) localTerms.add(term);
        else constants.add(decode(term));
      });
    };
    inspect(rule.head);
    for (const atom of rule.body.filter((a) => !a.negative)) inspect(atom);
    if (constants.size > 1 || localTerms.size > 1 || (constants.size && localTerms.size))
      throw new Error(
        `Unsupported remote dependency in ${rule.id}: no local evidence route joins these principals.`,
      );
    // A helper cannot erase an exposed principal's ownership and thereby hide remote access.
    rule.head.args.forEach((term, index) => {
      const ownerTerm = /^[A-Z]/.test(term) ? localTerms.has(term) : constants.has(decode(term));
      if (
        ownerTerm &&
        protocol.local[rule.head.predicate]?.[index] !== "@self" &&
        !protocol.onlyAt[rule.head.predicate]
      )
        throw new Error(
          `Helper in ${rule.id} must declare the exposed principal as local ownership.`,
        );
    });
    for (const atom of rule.body.filter((a) => a.negative)) {
      const fixed = protocol.onlyAt[atom.predicate];
      if (fixed && (!constants.has(fixed) || constants.size !== 1))
        throw new Error(`Unsupported remote negation in ${rule.id}.`);
      protocol.local[atom.predicate]?.forEach((slot, i) => {
        if (slot !== "@self") return;
        const term = atom.args[i]!;
        if (/^[A-Z]/.test(term) ? !localTerms.has(term) : !constants.has(decode(term)))
          throw new Error(
            `Unsupported remote negation in ${rule.id}: absence is not complete local evidence.`,
          );
      });
    }
  }
}

export function distributedClosure(
  protocol: PlacementProtocol,
  rules: Rule[],
  principals: readonly string[],
  inputs: (owner: string) => PolicyFact[],
  evaluate: (input: PolicyFact[], program: Rule[]) => { facts: PolicyFact[] } = runSouffle,
) {
  const stores = Object.fromEntries(
    principals.map((owner) => [
      owner,
      evaluate(inputs(owner), bindLocalRules(protocol, rules, owner)).facts,
    ]),
  );
  const unique = new Map<string, PolicyFact>();
  for (const facts of Object.values(stores))
    for (const fact of facts) unique.set(factKey(fact), fact);
  const localFacts = [...unique.values()];
  const observerRules = rules.filter(
    (rule) =>
      protocol.observer.includes(rule.head.predicate) &&
      (!protocol.ruleLocations?.[rule.id] || protocol.ruleLocations[rule.id]!.includes("observer")),
  );
  const observer = evaluate(localFacts, observerRules).facts.filter((fact) =>
    protocol.observer.includes(fact.predicate),
  );
  for (const fact of observer) unique.set(factKey(fact), fact);
  return { stores, localFacts, observer, facts: [...unique.values()] };
}
