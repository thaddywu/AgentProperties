import type { PolicyFact } from "@rakazo/contracts";
import { factKey, formatFact } from "../datalog.js";
import { queryDatalog } from "../query.js";
import { contains, evaluate, f, parseInputs, parseTarget, REASONING_RULES } from "./policy.js";
import type { RuntimeState } from "./runtime.js";
import { inputs, NovaRuntime, REPLIES } from "./runtime.js";

export type ProofNode = {
  fact: string;
  kind: "input" | "derived" | "absence" | "comparison";
  rule?: string;
  children: ProofNode[];
};
export function why(input: PolicyFact[], query: string): ProofNode | null {
  const target = parseTarget(query),
    result = evaluate(input),
    inputKeys = new Set(input.map(factKey));
  if (!contains(result.facts, target)) return null;
  const walk = (fact: PolicyFact): ProofNode => {
    const proof = result.proofs.get(factKey(fact));
    if (inputKeys.has(factKey(fact)))
      return { fact: formatFact(fact), kind: "input", children: [] };
    if (!proof) throw new Error("Missing engine provenance.");
    return {
      fact: formatFact(fact),
      kind: "derived",
      rule: proof.rule,
      children: [
        ...proof.premises.map(walk),
        ...(proof.checks ?? []).map((c) => ({ fact: c.text, kind: c.kind, children: [] })),
      ],
    };
  };
  return walk(target);
}
export function whatIf(input: PolicyFact[], remove: string, add: string, query: string) {
  const removed = parseInputs(remove),
    added = parseInputs(add),
    target = parseTarget(query);
  const original = new Map(input.map((f) => [factKey(f), f]));
  for (const f of removed)
    if (!original.delete(factKey(f)))
      throw new Error(`REMOVE fact is not in the selected input state: ${formatFact(f)}`);
  for (const f of added) original.set(factKey(f), f);
  const before = evaluate(input),
    after = evaluate([...original.values()]);
  const beforeKeys = new Set(before.facts.map(factKey)),
    afterKeys = new Set(after.facts.map(factKey));
  return {
    result: contains(after.facts, target),
    added: after.facts.filter((f) => !beforeKeys.has(factKey(f)) && after.proofs.has(factKey(f))),
    removed: before.facts.filter(
      (f) => !afterKeys.has(factKey(f)) && before.proofs.has(factKey(f)),
    ),
  };
}
export type Preventable = { name: string; records: PolicyFact[] };
export const PREVENTABLE_PRESET = `eP:\n  Receiver(auditor_a, mP).\n  Received(auditor_a, mP).\neF:\n  Receiver(auditor_a, mF).\n  Received(auditor_a, mF).`;
export function parsePreventable(source: string): Preventable[] {
  const groups: { name: string; source: string }[] = [];
  for (const line of source.split("\n")) {
    if (!line.trim() || line.trim().startsWith("%")) continue;
    const name = /^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*$/.exec(line);
    if (name) groups.push({ name: name[1]!, source: "" });
    else {
      const group = groups.at(-1);
      if (!group) throw new Error("Start each event with a name followed by a colon.");
      group.source += `${line}\n`;
    }
  }
  if (groups.length > 12)
    throw new Error("At most 12 preventable events (4,096 subsets) per analysis.");
  if (new Set(groups.map((g) => g.name)).size !== groups.length)
    throw new Error("Event names must be unique.");
  return groups.map((g) => {
    const records = parseInputs(g.source);
    if (!records.length) throw new Error(`Event ${g.name} has no input records.`);
    return { name: g.name, records };
  });
}
export function minimalPrevention(input: PolicyFact[], events: Preventable[], query: string) {
  if (events.length > 12) throw new Error("At most 12 preventable events.");
  const target = parseTarget(query),
    keys = new Set(input.map(factKey));
  if (new Set(events.map((e) => e.name)).size !== events.length)
    throw new Error("Event names must be unique.");
  for (const e of events) {
    if (!e.records.length) throw new Error(`Empty event: ${e.name}`);
    for (const record of e.records) {
      parseInputs(`${formatFact(record)}.`);
      if (!keys.has(factKey(record)))
        throw new Error(`Event ${e.name} refers to an absent input fact: ${formatFact(record)}`);
    }
  }
  let evaluated = 0;
  for (let size = 0; size <= events.length; size++) {
    const solutions: string[][] = [];
    const visit = (start: number, selection: Preventable[]) => {
      if (selection.length === size) {
        const remove = new Set(selection.flatMap((e) => e.records.map(factKey)));
        const closure = evaluate(input.filter((f) => !remove.has(factKey(f))));
        evaluated++;
        if (!contains(closure.facts, target)) solutions.push(selection.map((e) => e.name));
        return;
      }
      for (let i = start; i <= events.length - (size - selection.length); i++)
        visit(i + 1, [...selection, events[i]!]);
    };
    visit(0, []);
    if (solutions.length) return { size, solutions, evaluated };
  }
  return { size: null, solutions: [], evaluated };
}
export type Action = {
  id: string;
  sender: string;
  receiver: string;
  project: string;
  part: string;
};
export const ACTIONS: Action[] = Object.entries(REPLIES).flatMap(([sender, reply]) =>
  ["auditor_a", "auditor_b"].map((receiver) => ({
    id: `${sender}->${receiver}`,
    sender,
    receiver,
    project: "nova",
    part: reply.part,
  })),
);
export const ACTION_PRESET = ACTIONS.map((a) => `${a.sender} -> ${a.receiver}`).join("\n");
export function parseActions(source: string): Action[] {
  const actions = source
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("%"));
  const result = actions.map((line) => {
    const [sender, receiver, extra] = line.split("->").map((t) => t.trim());
    const action = ACTIONS.find((a) => a.sender === sender && a.receiver === receiver);
    if (!action || extra !== undefined)
      throw new Error(
        `Unknown progress action: ${line}. Use department -> auditor_a or auditor_b.`,
      );
    return action;
  });
  if (new Set(result.map((a) => a.id)).size !== result.length) throw new Error("Duplicate action.");
  return result;
}
export type SearchEdge = {
  action: Action;
  classification: "denied" | "completion-preserving" | "dead-ending";
  proof?: ProofNode | null;
  successor?: SearchNode;
  trace?: Action[];
};
export type SearchNode = { finished: boolean; edges: SearchEdge[]; trace: Action[] | null };
export function applyAction(state: RuntimeState, action: Action) {
  if (!ACTIONS.some((a) => JSON.stringify(a) === JSON.stringify(action)))
    throw new Error("Action is outside the configured Nova domain.");
  const runtime = new NovaRuntime(state),
    reply = REPLIES[action.sender]!;
  let id = reply.id,
    suffix = 1;
  while (runtime.state.messages.some((m) => m.id === id)) id = `${reply.id}_${suffix++}`;
  runtime.send(action.sender, action.receiver, id, reply.body);
  if (!contains(runtime.closure().facts, f("Carries", id, action.project, action.part)))
    throw new Error(
      `Missing source lineage for ${action.sender}. Deliver the Board assignment first.`,
    );
  const proof = why(inputs(runtime.state), `DenyReceive(${action.receiver}, ${id})`);
  const decision = runtime.settle(id);
  return { runtime, allowed: decision.allowed, proof };
}
export function speculative(state: RuntimeState, actions: Action[], goal: string) {
  const target = parseTarget(goal);
  if (actions.length > ACTIONS.length || new Set(actions.map((a) => a.id)).size !== actions.length)
    throw new Error("Invalid or duplicate action universe.");
  if (state.records.some((r) => r.fact.predicate === "Incoming"))
    throw new Error("Resolve pending deliveries first, or select the earlier runtime state.");
  let evaluated = 0;
  const search = (current: RuntimeState): SearchNode => {
    evaluated++;
    const closed = evaluate(inputs(current));
    if (contains(closed.facts, target)) return { finished: true, edges: [], trace: [] };
    const edges: SearchEdge[] = [];
    let trace: Action[] | null = null;
    for (const action of actions) {
      if (contains(closed.facts, f("Audited", action.project, action.part))) continue;
      const attempt = applyAction(current, action);
      if (!attempt.allowed) {
        edges.push({ action, classification: "denied", proof: attempt.proof });
        continue;
      }
      if (!contains(attempt.runtime.closure().facts, f("Audited", action.project, action.part)))
        throw new Error("Configured action did not make audit progress.");
      const successor = search(attempt.runtime.state);
      const completion = successor.trace === null ? undefined : [action, ...successor.trace];
      edges.push({
        action,
        classification: completion ? "completion-preserving" : "dead-ending",
        successor,
        trace: completion,
      });
      if (trace === null && completion) trace = completion;
    }
    return { finished: false, edges, trace };
  };
  return { ...search(state), evaluated };
}
export const terminalQuery = (state: RuntimeState, source: string) =>
  queryDatalog(inputs(state), REASONING_RULES, source);
