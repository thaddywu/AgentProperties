import { factKey } from "@rakazo/policy-runtime/datalog";
import { ACTIONS, applyAction, speculative } from "../analysis.js";
import { CONFIG } from "../config.js";
import { reconstructDebugView } from "../local-store.js";
import { f } from "../policy.js";
import type { Message } from "../runtime.js";
import { createEpisode, inputRecord, NovaRuntime } from "../runtime.js";
import { putRecord } from "../store-records.js";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { NOVA_GROUPS, NOVA_REQUIREMENTS, NOVA_TAGS, permitted } from "./oracle.js";

const departments = ["procurement", "facility", "hr"];
const orders = departments.flatMap((a) =>
  departments
    .filter((b) => a !== b)
    .map((b) => [a, b, departments.find((c) => c !== a && c !== b)!]),
);
const tagFor = (department: string) => NOVA_TAGS[departments.indexOf(department)]!;

/** Experimental no-gate comparator only. Never installed into the application. */
function bypassGate(runtime: NovaRuntime, id: string) {
  const message = runtime.state.messages.find((m) => m.id === id)!;
  runtime.state.stores[message.to] = runtime.state.stores[message.to]!.filter(
    (record) => factKey(record.fact) !== factKey(f("Incoming", message.to, id)),
  );
  for (const record of runtime.state.stores[message.to]!)
    if (record.fact.predicate === "TransportTag" && record.fact.args[0] === id)
      record.lifetime = "local";
  putRecord(runtime.state, inputRecord(f("Received", message.to, id), "runtime", message.to));
  message.status = "delivered";
  return { allowed: true, message };
}

type Totals = {
  workflows: number;
  attempts: number;
  expectedRefusals: number;
  violations: number;
  falseDenials: number;
  denied: number;
  deniedPayloadLeaks: number;
  deniedReceiptWrites: number;
  lineageErrors: number;
  completed: number;
  safelyCompleted: number;
  workflowsWithViolation: number;
  observerDisagreements: number;
};
const empty = (): Totals => ({
  workflows: 0,
  attempts: 0,
  expectedRefusals: 0,
  violations: 0,
  falseDenials: 0,
  denied: 0,
  deniedPayloadLeaks: 0,
  deniedReceiptWrites: 0,
  lineageErrors: 0,
  completed: 0,
  safelyCompleted: 0,
  workflowsWithViolation: 0,
  observerDisagreements: 0,
});

export function workflowPilot(mode: "disabled" | "enforced", policy?: NovaPolicyArtifact) {
  const groups: Record<string, Totals> = {
    sequential: empty(),
    interleaved: empty(),
    retryOtherAuditor: empty(),
  };
  const deadEnds: { order: string[]; routing: number; grantB: boolean; strategy: string }[] = [];
  const started = performance.now();
  for (const strategy of Object.keys(groups))
    for (const grantB of [false, true])
      for (const order of orders)
        for (let routing = 0; routing < 8; routing++) {
          const totals = groups[strategy]!;
          const runtime = createEpisode("initial", policy);
          if (grantB) runtime.configure([...CONFIG, f("HasCap", "auditor_b", "hr_review")]);
          for (const [i, department] of departments.entries())
            runtime.assign(`source${i}`, department, tagFor(department), "synthetic assignment");
          const known = new Map(["auditor_a", "auditor_b"].map((p) => [p, new Set<string>()]));
          let violations = 0;
          let attempts = 0;
          const send = (department: string, recipient: string, id: string) =>
            runtime.send(department, recipient, id, "synthetic review material");
          const settle = (message: Message) => {
            const incoming = message.labels.map((f) => f.args[1]!);
            const expectedTag = tagFor(message.from);
            if (incoming.length !== 1 || incoming[0] !== expectedTag) totals.lineageErrors++;
            const expected = permitted({
              recipient: message.to,
              known: [...known.get(message.to)!],
              incoming: [expectedTag],
              capabilities: message.to === "auditor_a" || grantB ? ["hr_review"] : [],
              requirements: NOVA_REQUIREMENTS,
              groups: NOVA_GROUPS,
            });
            const result =
              mode === "disabled" ? bypassGate(runtime, message.id) : runtime.settle(message.id);
            attempts++;
            if (!expected) totals.expectedRefusals++;
            if (result.allowed && !expected) {
              violations++;
              totals.violations++;
            }
            if (!result.allowed && expected) totals.falseDenials++;
            if (result.allowed) for (const tag of incoming) known.get(message.to)!.add(tag);
            else {
              totals.denied++;
              if (runtime.accessible(message.to).some((m) => m.id === message.id))
                totals.deniedPayloadLeaks++;
              if (
                runtime.state.stores[message.to]!.some(
                  (r) => factKey(r.fact) === factKey(f("Received", message.to, message.id)),
                )
              )
                totals.deniedReceiptWrites++;
            }
            return result.allowed;
          };
          const pending: Message[] = [];
          for (const [i, department] of order.entries()) {
            const recipient = routing & (1 << i) ? "auditor_b" : "auditor_a";
            const message = send(department, recipient, `reply${i}`);
            if (strategy === "interleaved") pending.push(message);
            else if (!settle(message) && strategy === "retryOtherAuditor")
              settle(
                send(
                  department,
                  recipient === "auditor_a" ? "auditor_b" : "auditor_a",
                  `retry${i}`,
                ),
              );
          }
          for (const message of pending) settle(message);
          const complete = NOVA_TAGS.every((tag) =>
            [...known.values()].some((tags) => tags.has(tag)),
          );
          const observed = reconstructDebugView(runtime.state).facts.some(
            (fact) => factKey(fact) === factKey(f("Finished", "nova")),
          );
          totals.workflows++;
          totals.attempts += attempts;
          if (complete) totals.completed++;
          if (complete && !violations) totals.safelyCompleted++;
          if (violations) totals.workflowsWithViolation++;
          if (complete !== observed) totals.observerDisagreements++;
          if (!complete && strategy === "retryOtherAuditor" && !grantB && deadEnds.length < 3)
            deadEnds.push({ order, routing, grantB, strategy });
        }
  return {
    workload:
      "Six department orders × eight initial routes × two capability configurations × three scripted scheduling/retry strategies = 288 workflows per condition",
    scope:
      "Deterministic actual Nova send/settle workflows; not autonomous LLM agents or a general task-completion study. No-gate control bypasses receive authorization only and retains label instrumentation.",
    groups,
    deadEnds,
    elapsedMs: Math.round(performance.now() - started),
    timingScope:
      "Exploratory wall time, affected by native evaluator cache and execution order; not a performance comparison",
  };
}

export function boundaryPilot() {
  const results: { id: string; expected: string; observed: unknown; passed: boolean }[] = [];
  const missing = createEpisode();
  missing.state.stores.auditor_a = missing.state.stores.auditor_a!.filter(
    (r) => !(r.fact.predicate === "TransportTag" && r.fact.args[0] === "mH"),
  );
  const before = JSON.stringify(missing.snapshot());
  let refusedMissingEnvelope = false;
  try {
    missing.settle("mH");
  } catch {
    refusedMissingEnvelope = true;
  }
  results.push({
    id: "missing-envelope",
    expected: "Abort without committing or releasing body",
    observed: { refusedMissingEnvelope, unchanged: before === JSON.stringify(missing.snapshot()) },
    passed: refusedMissingEnvelope && before === JSON.stringify(missing.snapshot()),
  });

  const pending = createEpisode("earlier");
  pending.send("facility", "auditor_a", "f_pending", "facility");
  pending.send("hr", "auditor_a", "h_pending", "hiring");
  const decisions = [pending.settle("f_pending").allowed, pending.settle("h_pending").allowed];
  results.push({
    id: "interleaved-receives",
    expected: "Recheck knowledge at each actual settle",
    observed: decisions,
    passed: JSON.stringify(decisions) === "[true,false]",
  });

  const revoked = new NovaRuntime();
  revoked.send("board", "auditor_a", "revoked", "hiring", { tag: "nova_hiring" });
  revoked.configure(CONFIG.filter((f) => !(f.predicate === "HasCap" && f.args[0] === "auditor_a")));
  const revocationDenied = !revoked.settle("revoked").allowed;
  results.push({
    id: "revoked-before-delivery",
    expected: "Use current committed capability state",
    observed: revocationDenied,
    passed: revocationDenied,
  });

  const refused = new NovaRuntime();
  refused.send("board", "auditor_b", "blocked", "hiring", { tag: "nova_hiring" });
  const denied = !refused.settle("blocked").allowed;
  refused.send("auditor_b", "auditor_a", "after_denial", "ordinary output");
  const inherited = refused.state.messages.find((m) => m.id === "after_denial")!.labels;
  results.push({
    id: "refused-lineage",
    expected: "Denied information does not label later output",
    observed: { denied, inherited },
    passed: denied && inherited.length === 0,
  });

  const relay = new NovaRuntime();
  relay.assign("input", "hr", "nova_hiring", "hiring");
  const rewritten = relay.send(
    "hr",
    "auditor_b",
    "rewritten",
    "a rewritten summary without a label claim",
  );
  const rewriteDenied = !relay.settle("rewritten").allowed;
  results.push({
    id: "rewritten-forwarding",
    expected: "Rewriting cannot remove tracked hiring protection",
    observed: { labels: rewritten.labels, denied: rewriteDenied },
    passed: rewriteDenied && rewritten.labels.some((f) => f.args[1] === "nova_hiring"),
  });

  const multi = new NovaRuntime();
  multi.assign("proc", "auditor_a", "nova_procurement", "procurement");
  multi.assign("fac", "auditor_a", "nova_facility", "facility");
  const bundled = multi.send("auditor_a", "auditor_b", "bundle", "two-part summary");
  const bundleAllowed = multi.settle("bundle").allowed;
  multi.send("board", "auditor_b", "third", "hiring", { tag: "nova_hiring" });
  multi.configure([...CONFIG, f("HasCap", "auditor_b", "hr_review")]);
  const thirdDenied = !multi.settle("third").allowed;
  results.push({
    id: "multi-label-forwarding",
    expected: "Carry both dependencies and prevent accumulation of the third",
    observed: { labelCount: bundled.labels.length, bundleAllowed, thirdDenied },
    passed: bundled.labels.length === 2 && bundleAllowed && thirdDenied,
  });

  const blind = new NovaRuntime();
  blind.send(
    "hr",
    "auditor_b",
    "unobserved",
    "synthetic hiring content from an uninstrumented source",
  );
  const blindAllowed = blind.settle("unobserved").allowed;
  results.push({
    id: "unobserved-source-boundary",
    expected: "Expose the instrumentation gap: content without a trusted label is not recognized",
    observed: { allowed: blindAllowed },
    passed: blindAllowed,
  });

  let unknownPrincipalRejected = false;
  try {
    new NovaRuntime().send("student_agent", "auditor_a", "new_agent", "hello");
  } catch {
    unknownPrincipalRejected = true;
  }
  results.push({
    id: "new-principal-boundary",
    expected: "Expose fixed Nova principal configuration",
    observed: { unknownPrincipalRejected },
    passed: unknownPrincipalRejected,
  });

  const earlier = createEpisode("earlier");
  const plan = speculative(earlier.state, ACTIONS, "Finished(nova)");
  let planned = earlier;
  for (const action of plan.trace ?? []) planned = applyAction(planned.state, action).runtime;
  const plannedComplete = reconstructDebugView(planned.state).facts.some(
    (f) => f.predicate === "Finished",
  );
  const deadEnd = createEpisode("earlier");
  deadEnd.send("facility", "auditor_a", "bad_choice", "facility");
  const legalChoice = deadEnd.settle("bad_choice").allowed;
  const blockedPlan = speculative(deadEnd.state, ACTIONS, "Finished(nova)");
  results.push({
    id: "completion-strategy",
    expected:
      "Planning finds a safe completion before a legal irreversible choice creates a dead end",
    observed: {
      trace: plan.trace?.map((a) => a.id),
      plannedComplete,
      legalChoice,
      deadEndHasPlan: blockedPlan.trace !== null,
    },
    passed: plannedComplete && legalChoice && blockedPlan.trace === null,
  });
  return results;
}

/** Actual sends under an admitted configuration change; fixed-config translation is a separate claim. */
export function configurationPilot(policy?: NovaPolicyArtifact) {
  const runtime = createEpisode("initial", policy);
  runtime.configure(
    CONFIG.filter((fact) => !(fact.predicate === "TagGroup" && fact.args[0] === "nova_hiring")),
  );
  const deliveries = NOVA_TAGS.map((tag, i) => {
    const recipient = i === 1 ? "auditor_b" : "auditor_a";
    return runtime.assign(`configured${i}`, recipient, tag, "synthetic audit part").allowed;
  });
  const facts = reconstructDebugView(runtime.state).facts;
  const successfulCoverage = new Set(
    runtime.state.messages
      .filter((m) => m.status === "delivered")
      .flatMap((m) => m.labels.map((f) => f.args[1]!)),
  );
  return {
    mutation: "Remove TagGroup(nova_hiring,nova), preserve AuditGoal and capability configuration",
    assumption:
      "The runtime accepts this configuration. If grouping is an application invariant, the adapter must enforce it; this probe does not assert the model was instructed to generalize beyond the supplied configuration.",
    deliveries,
    independentlyComplete: NOVA_TAGS.every((tag) => successfulCoverage.has(tag)),
    covered: facts
      .filter((f) => f.predicate === "Covered")
      .map((f) => f.args[0]!)
      .sort(),
    observerComplete: facts.some((f) => f.predicate === "Finished" && f.args[0] === "nova"),
  };
}
