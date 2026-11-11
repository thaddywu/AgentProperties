import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { CONFIG } from "./config.js";
import { localClosure, reconstructDebugView } from "./local-store.js";
import { contains, f } from "./policy.js";
import type { NovaRuntime, RuntimeState } from "./runtime.js";
import { createEpisode, inputs } from "./runtime.js";
import { PRINCIPALS } from "./shared.js";
import type { NovaPolicyArtifact } from "./translated-policy.js";
import { rulesFor } from "./translated-policy.js";

const keys = (facts: PolicyFact[]) => [...new Set(facts.map(factKey))].sort();
/** Diagnostic only: never use the full-copy closure to authorize a local delivery. */
export function closureConformance(state: RuntimeState) {
  const distributed = reconstructDebugView(state);
  const baseline = runSouffle(inputs(state), rulesFor(state)).facts;
  const local = new Set(keys(distributed.facts)),
    full = new Set(keys(baseline));
  const missing = [...full].filter((key) => !local.has(key));
  const extra = [...local].filter((key) => !full.has(key));
  const gates = state.messages
    .filter((m) => m.status === "pending")
    .map((message) => ({
      principal: message.to,
      message: message.id,
      localDeny: contains(distributed.stores[message.to]!, f("Deny", message.id, "message_policy")),
      fullCopyDeny: contains(baseline, f("Deny", message.id, "message_policy")),
    }));
  return {
    equivalent:
      !missing.length && !extra.length && gates.every((g) => g.localDeny === g.fullCopyDeny),
    localUnionCount: local.size,
    fullCopyCount: full.size,
    missing,
    extra,
    gates,
    storedInputCopies: Object.values(state.stores).reduce(
      (sum, records) => sum + records.length,
      0,
    ),
    fullCopyInputCopies: inputs(state).length * PRINCIPALS.length,
    scope:
      "Local closure union plus observer-only completion, and local gate decisions, at this snapshot. Not a proof for arbitrary executions or a minimum-storage claim.",
  };
}

type Observation = {
  message: string;
  recipient: string;
  allowed: boolean;
  expected: boolean;
  denyDerived: boolean;
  fullCopyDeny: boolean;
  received: boolean;
  bodyVisible: boolean;
};
type Case = {
  name: string;
  execute: (runtime: NovaRuntime, settle: (id: string, expected: boolean) => void) => void;
};
const cases: Case[] = [
  {
    name: "Unrestricted message",
    execute(r, settle) {
      r.send("hr", "auditor_b", "plain", "ordinary message");
      settle("plain", true);
    },
  },
  {
    name: "Capability missing",
    execute(r, settle) {
      r.send("board", "auditor_b", "restricted", "protected payload", { tag: "nova_hiring" });
      settle("restricted", false);
    },
  },
  {
    name: "Capability present",
    execute(r, settle) {
      r.send("board", "auditor_a", "permitted", "protected payload", { tag: "nova_hiring" });
      settle("permitted", true);
    },
  },
  {
    name: "Third distinct tag",
    execute(r, settle) {
      for (const [i, tag] of ["nova_procurement", "nova_facility", "nova_hiring"].entries()) {
        r.send("board", "auditor_a", `part${i}`, "protected part", { tag });
        settle(`part${i}`, i < 2);
      }
    },
  },
  {
    name: "All three incoming / Board exception",
    execute(r, settle) {
      r.configure([...CONFIG, f("HasCap", "board", "hr_review")]);
      for (const [i, tag] of ["nova_procurement", "nova_facility", "nova_hiring"].entries()) {
        r.send("board", "board", `source${i}`, "trusted input", { tag });
        settle(`source${i}`, true);
      }
      r.send("board", "auditor_a", "combined", "combined payload");
      settle("combined", false);
    },
  },
  {
    name: "Same-group non-goal tags",
    execute(r, settle) {
      r.configure([
        ...CONFIG,
        ...["alpha", "beta", "gamma"].map((tag) => f("TagGroup", tag, "other")),
      ]);
      for (const [i, tag] of ["alpha", "beta", "gamma"].entries()) {
        r.send("board", "auditor_b", `extra${i}`, "other project", { tag });
        settle(`extra${i}`, i < 2);
      }
    },
  },
  {
    name: "Repeated tag and unrelated group",
    execute(r, settle) {
      r.configure([...CONFIG, f("TagGroup", "unrelated", "other")]);
      for (const [i, tag] of ["nova_procurement", "nova_procurement", "unrelated"].entries()) {
        r.send("board", "auditor_b", `repeat${i}`, "tagged message", { tag });
        settle(`repeat${i}`, true);
      }
    },
  },
  {
    name: "Split audit completion",
    execute(r, settle) {
      for (const [i, tag] of ["nova_procurement", "nova_facility", "nova_hiring"].entries()) {
        r.send("board", i === 1 ? "auditor_b" : "auditor_a", `audit${i}`, "audit material", {
          tag,
        });
        settle(`audit${i}`, true);
      }
      if (!contains(reconstructDebugView(r.state).facts, f("Finished", "nova")))
        throw new Error("Global query did not combine local audit coverage.");
    },
  },
];
function trial(test: Case, policy?: NovaPolicyArtifact) {
  const runtime = createEpisode("initial", policy);
  const observations: Observation[] = [];
  let error: string | null = null;
  try {
    test.execute(runtime, (id, expected) => {
      const fullCopyDeny = contains(
        runSouffle(inputs(runtime.state), rulesFor(runtime.state)).facts,
        f("Deny", id, "message_policy"),
      );
      const result = runtime.settle(id),
        recipient = result.message.to;
      observations.push({
        message: id,
        recipient,
        allowed: result.allowed,
        expected,
        fullCopyDeny,
        denyDerived: contains(result.evaluation.facts, f("Deny", id, "message_policy")),
        received: contains(
          localClosure(runtime.state, recipient).facts,
          f("Received", recipient, id),
        ),
        bodyVisible: runtime.accessible(recipient).some((message) => message.id === id),
      });
    });
  } catch (cause) {
    error = cause instanceof Error ? cause.message : "Trial failed";
  }
  const facts = keys(reconstructDebugView(runtime.state).facts);
  const closureEquivalent =
    JSON.stringify(facts) ===
    JSON.stringify(keys(runSouffle(inputs(runtime.state), rulesFor(runtime.state)).facts));
  const visible = PRINCIPALS.map((principal) => ({
    principal,
    messages: runtime.accessible(principal).map((m) => m.id),
  }));
  return {
    observations,
    error,
    facts,
    visible,
    closureEquivalent,
    passed:
      !error &&
      closureEquivalent &&
      observations.every(
        (o) =>
          o.allowed === o.expected &&
          o.denyDerived === o.fullCopyDeny &&
          o.received === o.allowed &&
          (o.allowed || !o.bodyVisible),
      ),
  };
}
/** Independent isolated sessions, actual send/settle and recipient payload access. */
export function comparePrevention(policy?: NovaPolicyArtifact) {
  return cases.map((test) => {
    const golden = trial(test);
    const translated = policy ? trial(test, policy) : null;
    const matches = translated ? JSON.stringify(golden) === JSON.stringify(translated) : null;
    const difference = translated
      ? {
          missingFacts: golden.facts.filter((fact) => !translated.facts.includes(fact)),
          extraFacts: translated.facts.filter((fact) => !golden.facts.includes(fact)),
          decisionsChanged:
            JSON.stringify(golden.observations) !== JSON.stringify(translated.observations),
          visibilityChanged: JSON.stringify(golden.visible) !== JSON.stringify(translated.visible),
        }
      : null;
    return { name: test.name, golden, translated, matches, difference };
  });
}
