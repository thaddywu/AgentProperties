import { createHash } from "node:crypto";
import type { PolicyFact, Rule } from "./datalog.js";
import { evaluateDatalog, factKey } from "./datalog.js";
import { acceptsFact, distributedClosure, validateRuleLocality } from "./distributed.js";
import type { MessagingProfile } from "./messaging.js";
import {
  decode,
  encodeFact,
  encodeRule,
  limits,
  parseProgram,
  validateAndStratify,
} from "./query.js";

export type ProtocolWitness = { id: string; stores: Record<string, PolicyFact[]> };
export type ProtocolPlan = {
  replicateAt: Record<string, string[]>;
  ruleLocations: Record<string, string[]>;
};
export type PlacementChoice = { name: string; choices: string[][] };
const digest = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const keys = (facts: PolicyFact[]) => [...new Set(facts.map(factKey))].sort();
const union = (stores: Record<string, PolicyFact[]>) => [
  ...new Map(
    Object.values(stores)
      .flat()
      .map((f) => [factKey(f), f]),
  ).values(),
];
const evaluate = (input: PolicyFact[], rules: Rule[]) => ({
  facts: evaluateDatalog(input.map(encodeFact), rules, limits).facts.map((fact) => ({
    ...fact,
    args: fact.args.map(decode),
  })),
});
export const protocolProgramId = (profile: MessagingProfile) =>
  digest({
    principals: profile.principals,
    sourceAuthorities: profile.sourceAuthorities,
    configuration: profile.configuration,
    replicateAt: profile.replicateAt,
    predicates: profile.predicates,
    rules: profile.rules,
    ruleEncoding: profile.ruleEncoding,
    protocol: profile.protocol,
    roles: profile.roles,
  });

/** Exact minimization in a declared finite deployment space and finite witness domain. */
export function synthesizeProtocol(options: {
  profile: MessagingProfile;
  witnesses: ProtocolWitness[];
  storage: PlacementChoice[];
  inference?: PlacementChoice[];
  queries?: { owner: string; source: string }[];
  weights?: { facts: number; rules: number; replication: number };
  maxPlans?: number;
}) {
  const { profile, witnesses } = options;
  const slots = [
    ...options.storage.map((slot) => ({ ...slot, kind: "storage" as const })),
    ...(options.inference ?? []).map((slot) => ({ ...slot, kind: "inference" as const })),
  ];
  if (!witnesses.length || new Set(witnesses.map((w) => w.id)).size !== witnesses.length)
    throw new Error("Protocol synthesis needs uniquely named witnesses.");
  if (new Set(slots.map((s) => `${s.kind}:${s.name}`)).size !== slots.length)
    throw new Error("Duplicate placement search slot.");
  const weights = options.weights ?? { facts: 1, rules: 1, replication: 1 };
  if (Object.values(weights).some((weight) => !Number.isFinite(weight) || weight < 0))
    throw new Error("Protocol costs must be finite and nonnegative.");
  const totalPlans = slots.reduce((count, slot) => count * slot.choices.length, 1);
  if (!Number.isSafeInteger(options.maxPlans ?? 4096) || (options.maxPlans ?? 4096) < 1)
    throw new Error("Exact-search budget must be a positive finite integer.");
  if (!totalPlans || totalPlans > (options.maxPlans ?? 4096))
    throw new Error(
      "Declared protocol space exceeds the exact-search budget; no optimum was computed.",
    );
  for (const slot of slots) {
    const rule = profile.rules.find((rule) => rule.id === slot.name);
    if (slot.kind === "storage" ? !profile.protocol.replicated.includes(slot.name) : !rule)
      throw new Error("Search can only place declared shareable inputs and existing rules.");
    for (const sites of slot.choices) {
      if (!sites.length || new Set(sites).size !== sites.length)
        throw new Error("Placement choices need distinct nonempty sites.");
      const observerRule = rule && profile.protocol.observer.includes(rule.head.predicate);
      if (
        sites.some((site) =>
          observerRule ? site !== "observer" : !profile.principals.includes(site),
        )
      )
        throw new Error("Placement violates the declared store/observer boundary.");
      if (
        slot.kind === "storage" &&
        profile.protocol.onlyAt[slot.name] &&
        sites.some((s) => s !== profile.protocol.onlyAt[slot.name])
      )
        throw new Error("Placement violates input authority.");
    }
  }
  const rules =
    profile.ruleEncoding === "raw" ? profile.rules.map(encodeRule) : structuredClone(profile.rules);
  validateAndStratify([], rules);
  validateRuleLocality(profile.protocol, rules);
  const queries = (options.queries ?? []).map((query) => {
    if (query.owner !== "observer" && !profile.principals.includes(query.owner))
      throw new Error("Query observation has an unknown store.");
    const parsed = parseProgram(query.source);
    if (parsed.facts.length || parsed.rules.length !== 1 || parsed.rules[0]!.id !== "query")
      throw new Error("Protocol query observations must be read-only.");
    for (const atom of parsed.rules[0]!.body)
      if (profile.predicates[atom.predicate]?.args.length !== atom.args.length)
        throw new Error("Unknown protocol query predicate or arity.");
    validateAndStratify([], parsed.rules);
    return { ...query, rules: parsed.rules };
  });
  const queryKeys = (facts: PolicyFact[], query: Rule[]) =>
    keys(evaluate(facts, query).facts.filter((f) => f.predicate === "QueryResult"));
  const baselines = witnesses.map((witness) => {
    if (
      Object.keys(witness.stores).some((site) => !profile.principals.includes(site)) ||
      profile.principals.some((site) => !witness.stores[site])
    )
      throw new Error("Witness stores must match the profile.");
    for (const [site, inputs] of Object.entries(witness.stores))
      for (const fact of inputs) {
        const schema = profile.predicates[fact.predicate];
        if (
          schema?.kind !== "input" ||
          schema.args.length !== fact.args.length ||
          fact.args.some((arg) => typeof arg !== "string" || arg.length > 1024) ||
          !acceptsFact(profile.protocol, site, fact)
        )
          throw new Error("Witness contains invalid or misplaced input evidence.");
      }
    const facts = evaluate(union(witness.stores), rules).facts;
    const original = distributedClosure(
      profile.protocol,
      rules,
      profile.principals,
      (site) => witness.stores[site]!,
      evaluate,
    );
    return {
      witness,
      facts: keys(facts),
      denials: new Set(facts.filter((f) => f.predicate === profile.roles.deny).map(factKey)),
      queries: queries.map((q) =>
        queryKeys(q.owner === "observer" ? original.facts : original.stores[q.owner]!, q.rules),
      ),
    };
  });
  let examined = 0,
    feasible = 0;
  let best:
    | {
        plan: ProtocolPlan;
        cost: number;
        components: { facts: number; rules: number; replication: number };
      }
    | undefined;
  const visit = (index: number, plan: ProtocolPlan) => {
    if (index < slots.length) {
      const slot = slots[index]!;
      for (const sites of slot.choices)
        visit(
          index + 1,
          slot.kind === "storage"
            ? { ...plan, replicateAt: { ...plan.replicateAt, [slot.name]: sites } }
            : { ...plan, ruleLocations: { ...plan.ruleLocations, [slot.name]: sites } },
        );
      return;
    }
    examined++;
    let factsCost = 0,
      replicationCost = 0;
    const protocol = {
      ...profile.protocol,
      ruleLocations: { ...profile.protocol.ruleLocations, ...plan.ruleLocations },
    };
    const rulesCost = profile.rules.reduce(
      (count, rule) =>
        count +
        (protocol.ruleLocations[rule.id]?.length ??
          (profile.protocol.observer.includes(rule.head.predicate)
            ? 1
            : profile.protocol.onlyAt[rule.head.predicate]
              ? 1
              : profile.principals.length)),
      0,
    );
    for (const baseline of baselines) {
      const stores = structuredClone(baseline.witness.stores);
      const all = union(stores);
      for (const [predicate, sites] of Object.entries(plan.replicateAt)) {
        const tuples = all.filter((f) => f.predicate === predicate);
        for (const site of profile.principals)
          stores[site] = stores[site]!.filter((f) => f.predicate !== predicate).concat(
            sites.includes(site) ? tuples : [],
          );
      }
      const result = distributedClosure(
        protocol,
        rules,
        profile.principals,
        (site) => stores[site]!,
        evaluate,
      );
      if (JSON.stringify(keys(result.facts)) !== JSON.stringify(baseline.facts)) return;
      if (
        queries.some(
          (query, i) =>
            JSON.stringify(
              queryKeys(
                query.owner === "observer" ? result.facts : result.stores[query.owner]!,
                query.rules,
              ),
            ) !== JSON.stringify(baseline.queries[i]),
        )
      )
        return;
      for (const [site, input] of Object.entries(stores))
        for (const intent of input.filter((f) => f.predicate === profile.roles.incoming)) {
          const denial = factKey({
            predicate: profile.roles.deny,
            args: [intent.args[0]!, intent.args[1]!],
          });
          if (
            result.stores[site]!.some((f) => factKey(f) === denial) !== baseline.denials.has(denial)
          )
            return;
        }
      factsCost += Object.values(stores).reduce(
        (count, facts) => count + new Set(facts.map(factKey)).size,
        0,
      );
      for (const predicate of profile.protocol.replicated)
        replicationCost +=
          all.filter((f) => f.predicate === predicate).length *
          Math.max(0, (plan.replicateAt[predicate]?.length ?? profile.principals.length) - 1);
    }
    feasible++;
    const cost =
      factsCost * weights.facts + rulesCost * weights.rules + replicationCost * weights.replication;
    if (!best || cost < best.cost)
      best = {
        plan: structuredClone(plan),
        cost,
        components: { facts: factsCost, rules: rulesCost, replication: replicationCost },
      };
  };
  visit(0, {
    replicateAt: Object.fromEntries(
      Object.entries(profile.replicateAt ?? {}).map(([p, sites]) => [p, [...sites]]),
    ),
    ruleLocations: {},
  });
  if (!best)
    throw new Error(
      "No deployment preserves full closure and local decisions on the declared witnesses.",
    );
  return {
    ...best,
    programId: protocolProgramId(profile),
    witnessesHash: digest({ witnesses, queries: options.queries ?? [] }),
    searchSpaceHash: digest(slots),
    plansExamined: examined,
    feasiblePlans: feasible,
    witnessesChecked: witnesses.length,
    queryObservations: queries.length,
    optimalWithinDeclaredSpace: true as const,
    proofScope:
      "Exact optimum over enumerated placements and provided snapshots; not a universal asynchronous protocol proof. Message transfer channels and source authority remain fixed constraints.",
    costScope:
      "Stored input tuples summed over witness snapshots, deployed rule copies, and additional replicated tuple copies; not network bytes, latency or production traffic.",
  };
}

export function applyProtocolPlan(
  profile: MessagingProfile,
  result: ReturnType<typeof synthesizeProtocol>,
): MessagingProfile {
  if (result.programId !== protocolProgramId(profile))
    throw new Error("Protocol plan belongs to another program/profile.");
  return {
    ...structuredClone(profile),
    replicateAt: structuredClone(result.plan.replicateAt),
    protocol: {
      ...structuredClone(profile.protocol),
      ruleLocations: {
        ...profile.protocol.ruleLocations,
        ...structuredClone(result.plan.ruleLocations),
      },
    },
  };
}
