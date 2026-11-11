import { compileApplicationPolicy, createPolicySession } from "@rakazo/policy-runtime/application";
import { createBackendPort } from "@rakazo/policy-runtime/backend-port";
import type { RuntimeBinding } from "@rakazo/policy-runtime/binding";
import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import { LIFECYCLE_PREDICATES } from "@rakazo/policy-runtime/lifecycle";
import type { MessagingProfile } from "@rakazo/policy-runtime/messaging";
import { createMessagingRuntime } from "@rakazo/policy-runtime/messaging";
import type { ProtocolWitness } from "@rakazo/policy-runtime/protocol-planner";
import { applyProtocolPlan, synthesizeProtocol } from "@rakazo/policy-runtime/protocol-planner";
import { novaMessagingProfile } from "./ports.js";
import type { NovaPolicyArtifact } from "./translated-policy.js";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const departments = ["procurement", "facility", "hr"];
const tags = ["nova_procurement", "nova_facility", "nova_hiring"];

export function novaProtocolWitnesses(profile: MessagingProfile) {
  const snapshots = new Map<string, ProtocolWitness>();
  for (const grantB of [false, true])
    for (const order of [departments, [...departments].reverse()])
      for (const mask of [0, 2, 5, 7]) {
        const runtime = createMessagingRuntime(profile);
        if (grantB)
          runtime.configure([
            ...profile.configuration,
            f("AgentHasCapability", "auditor_b", "hr_review"),
          ]);
        const capture = () => {
          const stores = Object.fromEntries(
            Object.entries(runtime.state.stores).map(([owner, rows]) => [
              owner,
              rows.map((r) => r.fact),
            ]),
          );
          const key = JSON.stringify(
            Object.entries(stores).map(([owner, facts]) => [owner, facts.map(factKey).sort()]),
          );
          if (!snapshots.has(key)) snapshots.set(key, { id: `state-${snapshots.size}`, stores });
        };
        capture();
        for (const [i, department] of departments.entries()) {
          runtime.send("board", department, `source${i}`, "synthetic source", { tag: tags[i]! });
          capture();
          runtime.settle(`source${i}`);
          capture();
        }
        for (const [i, department] of order.entries()) {
          runtime.send(
            department,
            mask & (1 << i) ? "auditor_b" : "auditor_a",
            `reply${i}`,
            "synthetic report",
          );
          capture();
          runtime.settle(`reply${i}`);
          capture();
        }
        runtime.send("auditor_a", "auditor_b", "relay", "combined report");
        capture();
        runtime.settle("relay");
        capture();
        runtime.send("auditor_b", "board", "return_report", "return report");
        capture();
        runtime.settle("return_report");
        capture();
        runtime.send("board", "auditor_a", "board_relay", "forwarded report");
        capture();
        runtime.settle("board_relay");
        capture();
      }
  return [...snapshots.values()];
}

export async function novaBackendTrial(profile = novaMessagingProfile()) {
  const delivered: { id: string; recipient: string }[] = [];
  const port = createBackendPort({
    profile,
    deliver: async (message) => {
      delivered.push({ id: message.id, recipient: message.to });
    },
  });
  for (const [i, department] of departments.entries())
    await port.ingest({
      authority: "board",
      recipient: department,
      id: `source${i}`,
      body: "synthetic assignment",
      tag: tags[i]!,
    });
  await port.bind("procurement").send("auditor_a", "p", "procurement");
  await port.bind("facility").send("auditor_b", "f", "facility");
  const rejected = await port.bind("hr").send("auditor_b", "h_forbidden", "hiring");
  const accepted = await port.bind("hr").send("auditor_a", "h", "hiring");
  const auditComplete = port
    .inspect()
    .facts.some((fact) => factKey(fact) === factKey(f("Finished", "nova")));
  return {
    deniedMissingCapability: !rejected.allowed,
    deniedBodyReleased: delivered.some((m) => m.id === "h_forbidden"),
    hiringDeliveredToAuthorizedAuditor: accepted.allowed,
    auditComplete,
    auditorAKnows: port.bind("auditor_a").query('?- Knows("auditor_a", T).').rows.flat().sort(),
    delivered,
  };
}

export async function novaReportFsmTrial(auditComplete: boolean) {
  const inputs = [
    f("ResourceType", "report", "audit_report"),
    f("ResourceState", "report", "draft"),
    f("AllowedTransition", "audit_report", "approve", "draft", "approved"),
    f("AllowedTransition", "audit_report", "publish", "approved", "published"),
    f("AgentHasCapability", "reviewer", "approve_report"),
    f("AgentHasCapability", "publisher", "publish_report"),
    f("ReportGroup", "report", "nova"),
    // Explicit authorized observer-to-resource-authority observation, not an agent claim.
    ...(auditComplete ? [f("AuditComplete", "nova")] : []),
  ];
  const request = (action: string) => ({
    actor: action === "approve" ? "reviewer" : "publisher",
    action,
    resource: "report",
  });
  const binding: RuntimeBinding = {
    version: 1,
    id: "nova-report-fsm",
    context:
      "The trusted Nova adapter materializes AuditComplete from its authorized observer. The resource authority owns report state and actual approve/publish operations.",
    mechanisms: ["fsm"],
    predicates: {
      ...Object.fromEntries(
        Object.entries(LIFECYCLE_PREDICATES).map(([name, p]) => [
          name,
          { kind: p.kind, args: [...p.args], meaning: name },
        ]),
      ),
      AgentHasCapability: {
        kind: "input",
        args: ["Agent", "Capability"],
        meaning: "Authoritative grant.",
      },
      ReportGroup: {
        kind: "input",
        args: ["Resource", "Group"],
        meaning: "Trusted report registry.",
      },
      AuditComplete: {
        kind: "input",
        args: ["Group"],
        meaning: "Completion materialized by the authorized observer adapter.",
      },
      Request: {
        kind: "input",
        args: ["Request", "Actor", "Action"],
        meaning: "Runtime-created attempt.",
      },
      Allow: { kind: "derived", args: ["Request"], meaning: "Explicit permission." },
      Deny: {
        kind: "derived",
        args: ["Request", "Reason"],
        meaning: "Denial overrides permission.",
      },
    },
    decision: { request: "Request", allow: "Allow", deny: "Deny" },
    tests: [
      {
        name: "approve-completed-audit",
        inputs: [
          ...inputs.filter((f) => f.predicate !== "AuditComplete"),
          f("AuditComplete", "nova"),
        ],
        request: request("approve"),
        allowed: true,
      },
      { name: "cannot-publish-draft", inputs, request: request("publish"), allowed: false },
      {
        name: "incomplete-audit",
        inputs: inputs.filter((f) => f.predicate !== "AuditComplete"),
        request: request("approve"),
        allowed: false,
      },
    ],
  };
  const source =
    'Allow(Q) :- Request(Q, A, "approve"), Parameter(Q, "resource", R), AgentHasCapability(A, "approve_report"), ReportGroup(R, G), AuditComplete(G).\nAllow(Q) :- Request(Q, A, "publish"), Parameter(Q, "resource", R), AgentHasCapability(A, "publish_report").';
  const session = createPolicySession(binding, compileApplicationPolicy(binding, source), inputs);
  let callbacks = 0;
  const effect = async () => ++callbacks;
  const premature = await session.execute(request("publish"), effect);
  const approved = await session.execute(request("approve"), effect);
  const published = await session.execute(request("publish"), effect);
  return {
    prematurePublishDenied: !premature.allowed,
    approved: approved.allowed,
    published: published.allowed,
    callbacks,
    currentState: session.query('?- ResourceState("report", S).').rows,
    committedActions: callbacks,
  };
}

export async function runNovaPortDemo(policy?: NovaPolicyArtifact) {
  const profile = novaMessagingProfile(policy);
  const witnesses = novaProtocolWitnesses(profile);
  const queries = [
    { owner: "observer", source: "?- Finished(G)." },
    { owner: "auditor_a", source: '?- Knows("auditor_a", T).' },
    { owner: "auditor_b", source: '?- Knows("auditor_b", T).' },
    { owner: "auditor_a", source: "?- TagRequiresCapability(T,C)." },
  ];
  const baseline = synthesizeProtocol({ profile, witnesses, storage: [], queries });
  const all = [...profile.principals];
  const optimized = synthesizeProtocol({
    profile,
    witnesses,
    queries,
    storage: [
      { name: "AuditGoal", choices: [["board"], ["auditor_a", "auditor_b"], all] },
      { name: "Auditor", choices: [["auditor_a", "auditor_b"], all] },
      { name: "TagGroup", choices: [["auditor_a", "auditor_b"], all] },
      { name: "TagRequiresCapability", choices: [["hr", "auditor_a", "auditor_b"], all] },
    ],
    inference: [
      ...profile.rules
        .filter((rule) => rule.head.predicate === "Covered")
        .map((rule) => ({ name: rule.id, choices: [["auditor_a", "auditor_b"], all] })),
      {
        name: "runtime-dependency",
        choices: [["procurement", "facility", "hr", "auditor_a", "auditor_b"], all],
      },
    ],
  });
  const execution = await novaBackendTrial(applyProtocolPlan(profile, optimized));
  return {
    policyOrigin: policy ? { kind: "translated", id: policy.id } : { kind: "reference" },
    baseline,
    optimized,
    execution,
    fsm: await novaReportFsmTrial(execution.auditComplete),
  };
}
