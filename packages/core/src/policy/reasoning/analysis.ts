import type { PolicyFact } from "@rakazo/contracts";
import { factKey, formatFact } from "../datalog.js";
import { parseProgram } from "../query.js";
import { explainSouffle, runSouffle } from "./souffle.js";

export { ACTION_PRESET, PREVENTABLE_PRESET } from "./shared.js";

import { localClosure, localInputs, localRules, reconstructDebugView } from "./local-store.js";
import { contains, DERIVED, f, parseInputs, parseTarget } from "./policy.js";
import { PROTOCOL } from "./protocol.js";
import type { RuntimeState } from "./runtime.js";
import { clone, inputRecord, inputs, NovaRuntime, REPLIES } from "./runtime.js";

import { allRecords, filterRecords, putRecord } from "./store-records.js";

function without(context: RuntimeState, keys: Set<string>): RuntimeState {
  const changed = clone(context);
  filterRecords(changed, (r) => !keys.has(factKey(r.fact)));
  return changed;
}

export type ProofNode = {
  fact: string;
  kind: "input" | "derived" | "absence" | "comparison" | "protocol";
  rule?: string;
  children: ProofNode[];
};
export function why(input: RuntimeState, query: string, scope = "auditor_a"): ProofNode | null {
  const target = parseTarget(query);
  const stores =
    scope === "debug"
      ? reconstructDebugView(input).stores
      : { [scope]: localClosure(input, scope).facts };
  const owner = Object.keys(stores).find((owner) => contains(stores[owner]!, target));
  if (!owner) return null;
  const proof = explainSouffle(localInputs(input, owner), localRules(owner), target);
  const mark = (node: ProofNode) => {
    if (
      node.kind === "input" &&
      [PROTOCOL.transfers.message.import, PROTOCOL.transfers.audit.import].some((p) =>
        node.fact.startsWith(`${p}(`),
      )
    )
      node.kind = "protocol";
    node.children.forEach(mark);
  };
  mark(proof);
  return proof;
}

export function whatIf(input: RuntimeState, remove: string, add: string, query: string) {
  const removed = parseInputs(remove),
    added = parseInputs(add),
    target = parseTarget(query);
  const original = new Map(inputs(input).map((f) => [factKey(f), f]));
  for (const f of removed)
    if (!original.delete(factKey(f)))
      throw new Error(`REMOVE fact is not in the selected input state: ${formatFact(f)}`);
  const changed = without(input, new Set(removed.map(factKey)));
  for (const fact of added) {
    let owner: string | undefined;
    if (fact.predicate === "Before")
      owner = changed.messages.find((m) => m.id === fact.args[1])?.from;
    if (fact.predicate === "TrustedSource") owner = "board";
    if (fact.predicate === "TransportTag")
      owner = changed.messages.find((m) => m.id === fact.args[0])?.to;
    if (fact.predicate === "AuditReceipt") owner = PROTOCOL.transfers.audit.to;
    putRecord(changed, inputRecord(fact, "analysis", owner));
  }
  const before = reconstructDebugView(input),
    after = reconstructDebugView(changed);
  const beforeKeys = new Set(before.facts.map(factKey)),
    afterKeys = new Set(after.facts.map(factKey));
  return {
    result: contains(after.facts, target),
    added: after.facts.filter((f) => !beforeKeys.has(factKey(f)) && DERIVED.has(f.predicate)),
    removed: before.facts.filter((f) => !afterKeys.has(factKey(f)) && DERIVED.has(f.predicate)),
  };
}
export type Preventable = { name: string; records: PolicyFact[] };

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
export function minimalPrevention(input: RuntimeState, events: Preventable[], query: string) {
  if (events.length > 12) throw new Error("At most 12 preventable events.");
  const target = parseTarget(query),
    keys = new Set(inputs(input).map(factKey));
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
        const closure = reconstructDebugView(without(input, remove));
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
  tag: string;
};
export const ACTIONS: Action[] = Object.entries(REPLIES).flatMap(([sender, reply]) =>
  ["auditor_a", "auditor_b"].map((receiver) => ({
    id: `${sender}->${receiver}`,
    sender,
    receiver,
    tag: reply.tag,
  })),
);

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
  if (!contains(runtime.closure(action.sender).facts, f("Propagated", id, action.tag)))
    throw new Error(
      `Missing source lineage for ${action.sender}. Deliver the Board assignment first.`,
    );
  const proof = why(runtime.state, `DenyReceive(${action.receiver}, ${id})`, action.receiver);
  const decision = runtime.settle(id);
  return { runtime, allowed: decision.allowed, proof };
}
export function speculative(state: RuntimeState, actions: Action[], goal: string) {
  const target = parseTarget(goal);
  if (actions.length > ACTIONS.length || new Set(actions.map((a) => a.id)).size !== actions.length)
    throw new Error("Invalid or duplicate action universe.");
  if (allRecords(state).some((r) => r.fact.predicate === "Incoming"))
    throw new Error("Resolve pending deliveries first, or select the earlier runtime state.");
  let evaluated = 0;
  const search = (current: RuntimeState): SearchNode => {
    evaluated++;
    const closed = localClosure(current, "board");
    const selfIndex = PROTOCOL.local[target.predicate]?.indexOf("@self") ?? -1;
    const goalOwner =
      PROTOCOL.onlyAt[target.predicate] ?? (selfIndex >= 0 ? target.args[selfIndex] : undefined);
    const goalFacts = goalOwner
      ? localClosure(current, goalOwner).facts
      : reconstructDebugView(current).facts;
    if (contains(goalFacts, target)) return { finished: true, edges: [], trace: [] };
    const edges: SearchEdge[] = [];
    let trace: Action[] | null = null;
    for (const action of actions) {
      if (contains(closed.facts, f("Audited", action.tag))) continue;
      const attempt = applyAction(current, action);
      if (!attempt.allowed) {
        edges.push({ action, classification: "denied", proof: attempt.proof });
        continue;
      }
      if (!contains(attempt.runtime.closure(action.receiver).facts, f("Audited", action.tag)))
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
export function terminalQuery(state: RuntimeState, source: string, scope = "auditor_a") {
  const parsed = parseProgram(source);
  for (const fact of [...parsed.facts, ...parsed.rules.map((r) => r.head)])
    if (DERIVED.has(fact.predicate))
      throw new Error(`Derived predicate ${fact.predicate} is read-only.`);
  const facts = parsed.facts.map((f) => ({ ...f, args: f.args.map((a) => a.slice(2)) }));
  const snapshot =
    scope === "debug" ? reconstructDebugView(state).facts : localClosure(state, scope).facts;
  const result = runSouffle([...snapshot, ...facts], parsed.rules);
  return {
    columns: parsed.columns,
    rows: result.facts.filter((f) => f.predicate === "QueryResult").map((f) => f.args),
  };
}
