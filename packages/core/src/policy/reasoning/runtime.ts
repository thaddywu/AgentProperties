import type { PolicyFact } from "@rakazo/contracts";
import { factKey } from "../datalog.js";
import { CONFIG, contains, DERIVED, evaluate, f, validateInput } from "./policy.js";

export const PRINCIPALS = [
  "board",
  "procurement",
  "facility",
  "hr",
  "auditor_a",
  "auditor_b",
] as const;
export const NAMES: Record<string, string> = {
  board: "Executive Board",
  procurement: "Procurement",
  facility: "Facility",
  hr: "HR / Hiring",
  auditor_a: "Auditor A",
  auditor_b: "Auditor B",
};
export type InputRecord = {
  fact: PolicyFact;
  owner: string;
  source: "config" | "trusted app" | "runtime" | "analysis";
  event?: number;
  lifetime: "global" | "local" | "temporary";
};
export type Message = {
  id: string;
  from: string;
  to: string;
  body: string;
  status: "pending" | "delivered" | "denied";
  labels: PolicyFact[];
};
export type RuntimeEvent = {
  seq: number;
  kind: "send" | "receive" | "deny";
  message: string;
  actor: string;
  added: PolicyFact[];
  removed: PolicyFact[];
  before: InputRecord[];
  after: InputRecord[];
  check?: PolicyFact[];
  rule?: string;
};
export type RuntimeState = {
  records: InputRecord[];
  messages: Message[];
  events: RuntimeEvent[];
  revision: number;
};
export const clone = <T>(value: T): T => structuredClone(value);
export const inputs = (state: RuntimeState) => state.records.map((r) => r.fact);
const globalPredicates = new Set(["Auditor", "Requires"]);
export function inputRecord(
  fact: PolicyFact,
  source: InputRecord["source"],
  owner?: string,
): InputRecord {
  validateInput(fact);
  return {
    fact,
    source,
    owner: owner ?? (globalPredicates.has(fact.predicate) ? "global" : fact.args[0]!),
    lifetime:
      fact.predicate === "Incoming"
        ? "temporary"
        : globalPredicates.has(fact.predicate)
          ? "global"
          : "local",
  };
}
/** One observer-level logical view; records retain the real principal/event owner. */
export class NovaRuntime {
  state: RuntimeState;
  constructor(state?: RuntimeState) {
    this.state = state
      ? clone(state)
      : {
          records: CONFIG.map((f) => inputRecord(f, "config")),
          messages: [],
          events: [],
          revision: 0,
        };
  }
  snapshot() {
    return clone(this.state);
  }
  closure() {
    return evaluate(inputs(this.state));
  }
  private append(record: InputRecord) {
    if (!this.state.records.some((r) => factKey(r.fact) === factKey(record.fact)))
      this.state.records.push(record);
  }
  private event(
    kind: RuntimeEvent["kind"],
    msg: Message,
    before: InputRecord[],
    check?: PolicyFact[],
    rule?: string,
  ) {
    const after = clone(this.state.records),
      beforeKeys = new Set(before.map((r) => factKey(r.fact))),
      afterKeys = new Set(after.map((r) => factKey(r.fact)));
    const seq = ++this.state.revision;
    for (const r of this.state.records) if (!beforeKeys.has(factKey(r.fact))) r.event = seq;
    this.state.events.push({
      seq,
      kind,
      message: msg.id,
      actor: kind === "send" ? msg.from : msg.to,
      added: after.filter((r) => !beforeKeys.has(factKey(r.fact))).map((r) => r.fact),
      removed: before.filter((r) => !afterKeys.has(factKey(r.fact))).map((r) => r.fact),
      before,
      after: clone(this.state.records),
      check,
      rule,
    });
  }
  /** Only this application-owned entrypoint can introduce a trusted source tag. */
  assign(id: string, to: string, part: string, body: string) {
    this.send("board", to, id, body, { project: "nova", part });
    return this.settle(id);
  }
  /** Local send runtime computes temporal input facts from successful receive history. */
  send(
    from: string,
    to: string,
    id: string,
    body: string,
    trusted?: { project: string; part: string },
  ) {
    if (
      !PRINCIPALS.includes(from as (typeof PRINCIPALS)[number]) ||
      !PRINCIPALS.includes(to as (typeof PRINCIPALS)[number])
    )
      throw new Error("Unknown sender or receiver.");
    if (!/^[a-z][A-Za-z0-9_]*$/.test(id) || this.state.messages.some((m) => m.id === id))
      throw new Error("Message ID must be a new lowercase-leading identifier.");
    if (!body.trim()) throw new Error("Message body is required.");
    if (trusted && from !== "board")
      throw new Error("Only trusted Board assignment ingestion can attach a source tag.");
    const before = clone(this.state.records);
    this.append(inputRecord(f("Sender", from, id), "runtime", from));
    if (trusted)
      this.append(
        inputRecord(f("TrustedCarry", id, trusted.project, trusted.part), "trusted app", from),
      );
    // Source assignment is trusted ingestion, not a Board computation over its full history.
    if (!trusted)
      for (const record of before)
        if (record.fact.predicate === "Received" && record.fact.args[0] === from)
          this.append(inputRecord(f("Before", record.fact.args[1]!, id), "runtime", from));
    this.append(inputRecord(f("Incoming", to, id), "runtime", to));
    const labels = this.closure().facts.filter(
      (fact) => fact.predicate === "Carries" && fact.args[0] === id,
    );
    const message: Message = { id, from, to, body, labels, status: "pending" };
    this.state.messages.push(message);
    this.event("send", message, before);
    return clone(message);
  }
  /** Gate and delivery use the same Datalog program as all four analyses. */
  settle(id: string) {
    const msg = this.state.messages.find((m) => m.id === id);
    if (msg?.status !== "pending") throw new Error("Select a pending message.");
    const before = clone(this.state.records),
      evaluation = this.closure(),
      denial = f("DenyReceive", msg.to, id);
    const denied = contains(evaluation.facts, denial);
    this.state.records = this.state.records.filter(
      (r) => factKey(r.fact) !== factKey(f("Incoming", msg.to, id)),
    );
    if (!denied) {
      this.append(inputRecord(f("Receiver", msg.to, id), "runtime", msg.to));
      this.append(inputRecord(f("Received", msg.to, id), "runtime", msg.to));
    }
    msg.status = denied ? "denied" : "delivered";
    this.event(
      denied ? "deny" : "receive",
      msg,
      before,
      evaluation.facts,
      evaluation.proofs.get(factKey(denial))?.rule,
    );
    return { allowed: !denied, evaluation, message: clone(msg) };
  }
  accessible(principal: string) {
    return this.state.messages
      .filter((m) => m.from === principal || (m.to === principal && m.status === "delivered"))
      .map(clone);
  }
}
const assignments = [
  {
    to: "procurement",
    part: "procurement",
    id: "mP0",
    body: "Nova: prepare the $8M procurement budget rationale, including the supplier transition.",
  },
  {
    to: "facility",
    part: "facility",
    id: "mF0",
    body: "Nova: prepare the $3M facilities budget rationale, including the Building 4 consolidation.",
  },
  {
    to: "hr",
    part: "hiring",
    id: "m0",
    body: "Nova: prepare the $5M hiring budget rationale, including the Team Z hiring plan.",
  },
];
export const REPLIES: Record<string, { part: string; id: string; body: string }> = {
  procurement: {
    part: "procurement",
    id: "mP",
    body: "Procurement budget: $8M. Please review the Nova supplier-transition rationale.",
  },
  facility: {
    part: "facility",
    id: "mF",
    body: "Facility budget: $3M. Please review the Nova Building 4 consolidation rationale.",
  },
  hr: {
    part: "hiring",
    id: "mH",
    body: "Hiring budget: $5M. Please review the Nova Team Z hiring rationale.",
  },
};
/** Presets schedule actual send/gate/receive calls; they never load event or derived fixtures. */
export function createEpisode(preset: "initial" | "earlier" | "denial" = "denial") {
  const runtime = new NovaRuntime();
  if (preset === "initial") return runtime;
  for (const assignment of assignments)
    runtime.assign(assignment.id, assignment.to, assignment.part, assignment.body);
  const proc = REPLIES.procurement!;
  runtime.send("procurement", "auditor_a", proc.id, proc.body);
  runtime.settle(proc.id);
  if (preset === "denial") {
    const fac = REPLIES.facility!;
    runtime.send("facility", "auditor_a", fac.id, fac.body);
    runtime.settle(fac.id);
    const hr = REPLIES.hr!;
    runtime.send("hr", "auditor_a", hr.id, hr.body);
  }
  return runtime;
}
/** Presentation metadata only: no derived tuple is constructed here. */
export function derivedOwners(fact: PolicyFact, state: RuntimeState): string[] {
  switch (fact.predicate) {
    case "Knows":
    case "DenyReceive":
      return [fact.args[0]!];
    case "Finished":
      return ["board"];
    case "DependsOn":
      return [state.messages.find((m) => m.id === fact.args[0])?.from ?? "unknown"];
    case "Carries": {
      const m = state.messages.find((m) => m.id === fact.args[0]);
      return m ? [...new Set([m.from, ...(m.status === "delivered" ? [m.to] : [])])] : ["unknown"];
    }
    case "Audited":
      return [
        "board",
        ...state.messages
          .filter(
            (m) =>
              m.status === "delivered" &&
              contains(inputs(state), f("Auditor", m.to)) &&
              m.labels.some((l) => l.args[1] === fact.args[0] && l.args[2] === fact.args[1]),
          )
          .map((m) => m.to),
      ];
    default:
      return [];
  }
}
export function view(state: RuntimeState) {
  const result = evaluate(inputs(state));
  return {
    ...clone(state),
    derived: result.facts
      .filter((f) => DERIVED.has(f.predicate))
      .map((fact) => ({
        fact,
        owners: derivedOwners(fact, state),
        rule: result.proofs.get(factKey(fact))?.rule,
      })),
    finished: contains(result.facts, f("Finished", "nova")),
  };
}
