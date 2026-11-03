import type { PolicyFact, Rule } from "@rakazo/policy-runtime/datalog";
import { evaluateDatalog, factKey } from "@rakazo/policy-runtime/datalog";
import {
  decode,
  encodeFact,
  encodeRule,
  limits,
  validateAndStratify,
} from "@rakazo/policy-runtime/query";
import { f } from "../policy.js";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { rulesFor } from "../translated-policy.js";
import { NOVA_TAGS, subset } from "./oracle.js";

const outputs = ["DenyReceive", "HasReceivedTag", "Covered", "Finished"];
const projected = (facts: PolicyFact[], predicate: string) =>
  facts
    .filter((f) => f.predicate === predicate)
    .map(factKey)
    .sort();
function evaluate(inputs: PolicyFact[], rules: Rule[]) {
  return evaluateDatalog(inputs.map(encodeFact), rules, limits).facts.map((f) => ({
    ...f,
    args: f.args.map(decode),
  }));
}

/** Paired EDB tests with a graph-reachability oracle, including cycles and three-hop propagation. */
export function recursiveComparison(policy: NovaPolicyArtifact, removePropagationControl = false) {
  const reference = rulesFor({}).map(encodeRule);
  const translated = removePropagationControl
    ? reference.filter((r) => r.id !== "label-propagation")
    : structuredClone(rulesFor({ policy }));
  validateAndStratify([], reference);
  validateAndStratify([], translated);
  const edges = [
    [0, 1],
    [1, 2],
    [2, 3],
    [0, 2],
    [1, 3],
    [2, 1],
  ] as const;
  let snapshots = 0,
    oracleMismatches = 0;
  const mismatches = Object.fromEntries(outputs.map((p) => [p, 0]));
  const counterexamples: Record<string, unknown> = {};
  const byPriorState = Object.fromEntries(
    ["no_prior_exposure", "already_exposed"].map((name) => [
      name,
      { snapshots: 0, mismatches: Object.fromEntries(outputs.map((p) => [p, 0])) },
    ]),
  );
  for (let mask = 0; mask < 64; mask++)
    for (let labels = 0; labels < 8; labels++)
      for (const capability of [false, true])
        for (const grouped of [false, true]) {
          const seeds = subset(NOVA_TAGS, labels);
          const partition =
            byPriorState[grouped && seeds.length === 3 ? "already_exposed" : "no_prior_exposure"]!;
          partition.snapshots++;
          const chosen = edges.filter((_, i) => mask & (1 << i));
          const inputs = [
            f("Incoming", "auditor_a", "m3"),
            f("Auditor", "auditor_a"),
            f("AuditGoal", "nova", ...NOVA_TAGS),
            f("Requires", "nova_hiring", "hr_review"),
            ...[0, 1, 2, 3].map((i) => f("Sender", "auditor_a", `m${i}`)),
            ...[0, 1, 2].map((i) => f("Received", "auditor_a", `m${i}`)),
            ...chosen.map(([a, b]) => f("ReceivedBeforeSend", `m${a}`, `m${b}`)),
            ...seeds.map((t) => f("TransportTag", "m0", t)),
            ...NOVA_TAGS.filter((t) => grouped || t !== "nova_hiring").map((t) =>
              f("TagGroup", t, "nova"),
            ),
            ...(capability ? [f("HasCap", "auditor_a", "hr_review")] : []),
          ];
          const a = evaluate(inputs, reference),
            b = evaluate(inputs, translated);
          const reachable = new Set([0]);
          for (let i = 0; i < 4; i++)
            for (const [from, to] of chosen) if (reachable.has(from)) reachable.add(to);
          const expected = [...reachable]
            .flatMap((i) => seeds.map((t) => f("MessageTag", `m${i}`, t)))
            .map(factKey)
            .sort();
          if (JSON.stringify(projected(a, "MessageTag")) !== JSON.stringify(expected))
            oracleMismatches++;
          snapshots++;
          for (const p of outputs)
            if (JSON.stringify(projected(a, p)) !== JSON.stringify(projected(b, p))) {
              mismatches[p] = mismatches[p]! + 1;
              partition.mismatches[p] = partition.mismatches[p]! + 1;
              counterexamples[p] ??= {
                inputs,
                reference: projected(a, p),
                translated: projected(b, p),
              };
            }
        }
  return {
    status: "tested" as const,
    snapshots,
    mismatches,
    oracleMismatches,
    counterexamples,
    byPriorState,
    scope:
      "2,048 schema-valid EDBs: six optional graph edges (including a cycle), three seed labels, capability present/absent, hiring grouping present/absent. Some cyclic histories are not runtime-reachable; this is a Datalog semantics stress test, not a universal proof.",
    control: removePropagationControl
      ? "Handwritten missing-recursion control, not a deployable model output or an accuracy trial."
      : undefined,
  };
}
