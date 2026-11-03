import type { PolicyFact, Rule } from "@rakazo/policy-runtime/datalog";
import { evaluateDatalog, factKey } from "@rakazo/policy-runtime/datalog";
import { decode, encodeFact, limits } from "@rakazo/policy-runtime/query";
import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { localRules } from "../local-store.js";
import { f } from "../policy.js";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { NOVA_TAGS, permitted, subset } from "./oracle.js";

const normalize = (rules: Rule[]) => {
  const term = (value: string) =>
    /^[A-Z]/.test(value) || value.startsWith("c:") ? value : `c:${value}`;
  return rules.map((rule) => ({
    ...rule,
    head: { ...rule.head, args: rule.head.args.map(term) },
    body: rule.body.map((atom) => ({ ...atom, args: atom.args.map(term) })),
    distinct: rule.distinct.map(([a, b]): [string, string] => [term(a), term(b)]),
  }));
};
const selectedKeys = (facts: PolicyFact[]) =>
  facts
    .filter((f) => ["DenyReceive", "Covered", "HasReceivedTag", "MessageTag"].includes(f.predicate))
    .map(factKey)
    .sort();
const scenarios: { name: string; tags: string[]; groups: [string, string][] }[] = [
  { name: "configured-nova", tags: NOVA_TAGS, groups: NOVA_TAGS.map((tag) => [tag, "nova"]) },
  {
    name: "same-group-outside-goal",
    tags: ["extra_alpha", "extra_beta", "extra_gamma"],
    groups: ["extra_alpha", "extra_beta", "extra_gamma"].map((tag) => [tag, "other"]),
  },
  {
    name: "split-groups",
    tags: NOVA_TAGS,
    groups: NOVA_TAGS.map((tag, i) => [tag, i === 2 ? "other" : "nova"]),
  },
  {
    name: "ungrouped-goal-part",
    tags: NOVA_TAGS,
    groups: NOVA_TAGS.slice(0, 2).map((tag) => [tag, "nova"]),
  },
];

/** Enumerates a stated finite snapshot domain, not a universal equivalence proof. */
export function translationPilot(policy?: NovaPolicyArtifact) {
  const counts = {
    snapshots: 0,
    excludedAlreadyViolating: 0,
    decisionMatches: 0,
    falseAllows: 0,
    falseDenials: 0,
    coverageMismatches: 0,
    knowledgeMismatches: 0,
    nativeCrossChecks: 0,
  };
  const byScenario: Record<
    string,
    { snapshots: number; decisionErrors: number; coverageErrors: number }
  > = {};
  const counterexamples: {
    kind: string;
    scenario: string;
    recipient: string;
    known: string[];
    incoming: string[];
    capability: boolean;
    expected: unknown;
    observed: unknown;
  }[] = [];
  const seen = new Set<string>();
  for (const scenario of scenarios) {
    const tally = { snapshots: 0, decisionErrors: 0, coverageErrors: 0 };
    byScenario[scenario.name] = tally;
    for (const recipient of ["auditor_a", "auditor_b", "board"]) {
      const nativeRules = localRules(recipient, { policy });
      const rules = normalize(nativeRules);
      for (const capability of [false, true])
        for (let knownMask = 0; knownMask < 8; knownMask++)
          for (let incomingMask = 0; incomingMask < 8; incomingMask++) {
            const known = subset(scenario.tags, knownMask);
            const incoming = subset(scenario.tags, incomingMask);
            if (
              !permitted({
                recipient,
                known: [],
                incoming: known,
                capabilities: [],
                requirements: [],
                groups: scenario.groups,
              })
            ) {
              counts.excludedAlreadyViolating++;
              continue;
            }
            const expectedAllow = permitted({
              recipient,
              known,
              incoming,
              capabilities: capability ? ["hr_review"] : [],
              requirements: [[scenario.tags[2]!, "hr_review"]],
              groups: scenario.groups,
            });
            const inputs = [
              f("Incoming", recipient, "pending"),
              f("Received", recipient, "prior"),
              f("Auditor", "auditor_a"),
              f("Auditor", "auditor_b"),
              f("Requires", scenario.tags[2]!, "hr_review"),
              ...scenario.groups.map(([tag, group]) => f("TagGroup", tag, group)),
              ...known.map((tag) => f("TransportTag", "prior", tag)),
              ...incoming.map((tag) => f("TransportTag", "pending", tag)),
              ...(capability ? [f("HasCap", recipient, "hr_review")] : []),
            ];
            const facts = evaluateDatalog(inputs.map(encodeFact), rules, limits).facts.map(
              (fact) => ({ ...fact, args: fact.args.map(decode) }),
            );
            const observedAllow = !facts.some(
              (fact) => factKey(fact) === factKey(f("DenyReceive", recipient, "pending")),
            );
            const observedCoverage = facts
              .filter((f) => f.predicate === "Covered")
              .flatMap((f) => f.args)
              .sort();
            const expectedCoverage = recipient === "board" ? [] : [...known].sort();
            const observedKnowledge = facts
              .filter((f) => f.predicate === "HasReceivedTag")
              .map((f) => f.args[1]!)
              .sort();
            counts.snapshots++;
            tally.snapshots++;
            if (expectedAllow === observedAllow) counts.decisionMatches++;
            else {
              tally.decisionErrors++;
              if (observedAllow) counts.falseAllows++;
              else counts.falseDenials++;
            }
            const record = (kind: string, expected: unknown, observed: unknown) => {
              const key = `${kind}:${scenario.name}`;
              if (!seen.has(key)) {
                seen.add(key);
                counterexamples.push({
                  kind,
                  scenario: scenario.name,
                  recipient,
                  known,
                  incoming,
                  capability,
                  expected,
                  observed,
                });
              }
            };
            if (expectedAllow !== observedAllow) record("decision", expectedAllow, observedAllow);
            if (JSON.stringify(expectedCoverage) !== JSON.stringify(observedCoverage)) {
              counts.coverageMismatches++;
              tally.coverageErrors++;
              record("coverage", expectedCoverage, observedCoverage);
            }
            if (JSON.stringify([...known].sort()) !== JSON.stringify(observedKnowledge)) {
              counts.knowledgeMismatches++;
              record("knowledge", known, observedKnowledge);
            }
            // Deterministic engine cross-check; the actual workflow experiment uses native Soufflé.
            if (counts.snapshots % 29 === 0) {
              const native = runSouffle(inputs, nativeRules).facts;
              if (JSON.stringify(selectedKeys(facts)) !== JSON.stringify(selectedKeys(native)))
                throw new Error("TypeScript/native evaluator disagreement in the pilot.");
              counts.nativeCrossChecks++;
            }
          }
    }
  }
  return {
    domain:
      "Three known/incoming tags, four grouping configurations, three recipients, two current capability states; prior same-group exposure violations excluded. Revoked capabilities may coexist with prior knowledge.",
    corpusOrigin: "Exploratory post-generation probes, not a held-out accuracy benchmark",
    oracle: "Independent set-based interpretation of P2/P3 and successful-receipt coverage",
    counts,
    byScenario,
    counterexamples,
  };
}
