import type {
  PolicyArtifact,
  PolicyEvent,
  PolicyFact,
  PolicyLabel,
  PolicyPrincipal,
  PolicyState,
} from "@rakazo/contracts";
import { APP2_RULES, evaluateDatalog, factKey } from "./datalog.js";

export function emptyPolicyState(): PolicyState {
  return {
    version: 1,
    phase: 0,
    status: "ready",
    artifacts: {},
    local: {
      board: { artifacts: [], facts: [] },
      procurement: { artifacts: [], facts: [] },
      facility: { artifacts: [], facts: [] },
      hiring: { artifacts: [], facts: [] },
      auditor_a: { artifacts: [], facts: [] },
    },
    events: [],
    counters: {},
  };
}
const fact = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
export const messageFacts = (artifact: PolicyArtifact) =>
  artifact.carries.map((label) => fact("Carries", artifact.id, label.project, label.component));
const add = (state: PolicyState, owner: PolicyPrincipal, facts: PolicyFact[]) => {
  const all = [...state.local[owner].facts, ...facts];
  state.local[owner].facts = [...new Map(all.map((item) => [factKey(item), item])).values()];
};
const close = (state: PolicyState, owner: PolicyPrincipal) => {
  state.local[owner].facts = evaluateDatalog(
    state.local[owner].facts,
    APP2_RULES.filter((r) => r.stratum === 0),
  ).facts;
};
function record(
  state: PolicyState,
  event: Omit<PolicyEvent, "seq" | "before" | "after" | "incoming" | "rules" | "witnesses"> &
    Partial<Pick<PolicyEvent, "incoming" | "rules" | "witnesses">>,
  change: () => void,
) {
  const before = structuredClone(state.local);
  change();
  state.events.push({
    incoming: [],
    rules: [],
    witnesses: [],
    ...event,
    seq: state.events.length + 1,
    before,
    after: structuredClone(state.local),
  });
}
function storeArtifact(state: PolicyState, owner: PolicyPrincipal, artifact: PolicyArtifact) {
  if (state.artifacts[artifact.id])
    throw new Error("Artifact IDs are immutable and unique within a session");
  state.artifacts[artifact.id] = structuredClone(artifact);
  state.local[owner].artifacts.push(artifact.id);
  add(state, owner, messageFacts(artifact));
}
/** Trusted initialization only. No model/tool/API request can supply its own labels. */
export function createSource(
  state: PolicyState,
  owner: PolicyPrincipal,
  id: string,
  text: string,
  labels: PolicyLabel[] = [],
) {
  if (owner !== "board") throw new Error("Only Board may annotate source artifacts");
  const artifact: PolicyArtifact = { id, producer: owner, text, carries: labels, inputs: [] };
  record(state, { kind: "create", actor: owner, artifactId: id }, () =>
    storeArtifact(state, owner, artifact),
  );
}
export function accessibleArtifacts(state: PolicyState, owner: PolicyPrincipal): PolicyArtifact[] {
  return state.local[owner].artifacts.map((id) => structuredClone(state.artifacts[id]!));
}
/** The same complete input set is supplied to the model and recorded as dependencies. */
export async function computeArtifact(
  state: PolicyState,
  owner: PolicyPrincipal,
  id: string,
  generate: (inputs: PolicyArtifact[]) => Promise<{ text: string; model: string }>,
) {
  const inputs = accessibleArtifacts(state, owner);
  const result = await generate(structuredClone(inputs));
  if (!result.text.trim() || result.text.length > 16000)
    throw new Error("Invalid computation output");
  const edges = inputs.map((input) => fact("DerivedFrom", id, input.id));
  const closure = evaluateDatalog(
    [...state.local[owner].facts, ...edges],
    APP2_RULES.filter((r) => r.stratum === 0),
  );
  const carries = closure.facts
    .filter((f) => f.predicate === "Carries" && f.args[0] === id)
    .map((f) => ({ project: f.args[1]!, component: f.args[2]! }));
  record(state, { kind: "compute", actor: owner, artifactId: id, model: result.model }, () => {
    storeArtifact(state, owner, {
      id,
      producer: owner,
      text: result.text,
      carries,
      inputs: inputs.map((a) => a.id),
    });
    add(state, owner, edges);
    close(state, owner);
  });
}
/** Must run under the session's database lock. Evaluates before inserting any receiver data. */
export function deliverArtifact(
  state: PolicyState,
  sender: PolicyPrincipal,
  receiver: PolicyPrincipal,
  id: string,
) {
  if (!state.local[sender].artifacts.includes(id))
    throw new Error("Sender cannot access this artifact");
  const artifact = state.artifacts[id]!;
  const pair = [sender, receiver].sort().join(":");
  state.counters[pair] = (state.counters[pair] ?? 0) + 1;
  const messageId = `msg_${sender}_to_${receiver}_${state.counters[pair]}`;
  const base = { artifactId: id, messageId, from: sender, to: receiver };
  record(state, { ...base, kind: "send", actor: sender }, () => {});
  const incoming = [fact("Incoming", receiver, id), ...messageFacts(artifact)];
  const evaluation = evaluateDatalog([...state.local[receiver].facts, ...incoming], APP2_RULES);
  const denials = evaluation.facts.filter(
    (f) => f.predicate === "Deny" && f.args[0] === receiver && f.args[1] === id,
  );
  const rules = [...new Set(denials.map((f) => evaluation.proofs.get(factKey(f))!.rule))];
  const witnesses = denials.flatMap((f) => evaluation.proofs.get(factKey(f))!.premises);
  const allowed = denials.length === 0;
  record(
    state,
    {
      ...base,
      kind: "receive",
      actor: receiver,
      incoming,
      rules,
      witnesses,
      decision: allowed ? "allow" : "deny",
    },
    () => {
      if (!allowed) return;
      if (!state.local[receiver].artifacts.includes(id)) state.local[receiver].artifacts.push(id);
      add(state, receiver, [fact("Received", receiver, id), ...messageFacts(artifact)]);
      close(state, receiver);
    },
  );
  // Ephemeral Incoming/New/Deny and incoming Carries are never copied on failure.
  return allowed;
}
export function deliveryNotice(state: PolicyState, owner: PolicyPrincipal, text: string) {
  const id = `notice_${state.events.length + 1}`;
  record(state, { kind: "notice", actor: owner, artifactId: id }, () =>
    storeArtifact(state, owner, { id, producer: owner, text, carries: [], inputs: [] }),
  );
}
