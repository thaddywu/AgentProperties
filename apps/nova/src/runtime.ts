import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import { derivedAt, localClosure, reconstructDebugView } from "./local-store.js";
import { CONFIG, contains, f, validateInput } from "./policy.js";
import { migratePredicateNames } from "./predicate-migration.js";
import { accepts, PROTOCOL } from "./protocol.js";
import { PRINCIPALS } from "./shared.js";
import {
  allRecords,
  emptyStores,
  filterRecords,
  partitionLegacyRecords,
  putRecord,
} from "./store-records.js";
import { migrateTagSchema } from "./tag-migration.js";

import type { NovaPolicyArtifact } from "./translated-policy.js";
import { readPolicyArtifact } from "./translated-policy.js";

export { NAMES, PRINCIPALS } from "./shared.js";
export type InputRecord = {
  fact: PolicyFact;
  owner: string;
  source: "config" | "trusted app" | "runtime" | "analysis" | "protocol";
  event?: number;
  replicated?: boolean;
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
  before: LocalStores;
  after: LocalStores;
  check?: PolicyFact[];
  rule?: string;
};
export type LocalStores = Record<string, InputRecord[]>;
export type RuntimeState = {
  policy?: NovaPolicyArtifact;
  storeSchemaVersion: 1;
  protocolVersion?: 1 | 2 | 3;
  tagSchemaVersion?: 1;
  stores: LocalStores;
  messages: Message[];
  events: RuntimeEvent[];
  revision: number;
};
export type LegacyRuntimeState = Omit<RuntimeState, "stores" | "storeSchemaVersion" | "events"> & {
  records: InputRecord[];
  events: (Omit<RuntimeEvent, "before" | "after"> & {
    before: InputRecord[];
    after: InputRecord[];
  })[];
};
export const clone = <T>(value: T): T => structuredClone(value);
export const inputs = (state: RuntimeState) => [
  ...new Map(allRecords(state).map((r) => [factKey(r.fact), r.fact])).values(),
];
const replicatedPredicates = new Set<string>(PROTOCOL.replicated);
export function inputRecord(
  fact: PolicyFact,
  source: InputRecord["source"],
  owner?: string,
): InputRecord {
  validateInput(fact);
  const location = owner ?? (replicatedPredicates.has(fact.predicate) ? "*" : fact.args[0]!);
  if (location !== "*" && !accepts(location, fact))
    throw new Error(`Protocol rejects ${fact.predicate} at ${location}`);
  return {
    fact,
    source,
    owner: location,
    lifetime: PROTOCOL.temporary.some((p) => p === fact.predicate) ? "temporary" : "local",
  };
}
/** Stores share an in-process host, but each policy evaluation receives one owner only. */
export class NovaRuntime {
  state: RuntimeState;
  constructor(state?: RuntimeState | LegacyRuntimeState) {
    const policy =
      state && state.policy !== undefined ? readPolicyArtifact(state.policy) : undefined;
    if (state && "stores" in state)
      this.state = clone({
        ...(policy ? { policy } : {}),
        storeSchemaVersion: 1,
        protocolVersion: state.protocolVersion,
        tagSchemaVersion: state.tagSchemaVersion,
        stores: state.stores,
        messages: state.messages,
        events: state.events,
        revision: state.revision,
      });
    else if (state) {
      const legacy = clone(state);
      migrateTagSchema(legacy);
      migratePredicateNames(legacy);
      if (!legacy.protocolVersion) {
        legacy.records = migrateRecords(legacy.records, legacy.messages);
        for (const event of legacy.events) {
          event.before = migrateRecords(event.before, legacy.messages);
          event.after = migrateRecords(event.after, legacy.messages);
        }
      }
      const { records, events, ...rest } = legacy;
      this.state = {
        ...rest,
        ...(policy ? { policy } : {}),
        storeSchemaVersion: 1,
        protocolVersion: 1,
        stores: partitionLegacyRecords(records.filter((r) => r.fact.predicate !== "AuditReceipt")),
        events: events.map((event) => ({
          ...event,
          before: partitionLegacyRecords(
            event.before.filter((r) => r.fact.predicate !== "AuditReceipt"),
          ),
          after: partitionLegacyRecords(
            event.after.filter((r) => r.fact.predicate !== "AuditReceipt"),
          ),
        })),
      };
    } else {
      this.state = {
        storeSchemaVersion: 1,
        protocolVersion: 1,
        tagSchemaVersion: 1,
        stores: emptyStores(),
        messages: [],
        events: [],
        revision: 0,
      };
      for (const fact of CONFIG) putRecord(this.state, inputRecord(fact, "config"));
    }
    // Old summary facts are no longer runtime inputs. Keep messages and gate history.
    if (!this.state.protocolVersion || this.state.protocolVersion < 2) {
      const keep = (r: InputRecord) => r.fact.predicate !== "AuditReceipt";
      filterRecords(this.state, keep);
      for (const event of this.state.events) {
        filterRecords({ stores: event.before }, keep);
        filterRecords({ stores: event.after }, keep);
        event.added = event.added.filter((f) => f.predicate !== "AuditReceipt");
        event.removed = event.removed.filter((f) => f.predicate !== "AuditReceipt");
        event.check = event.check?.filter(
          (f) =>
            !["AuditReceipt", "Finished"].includes(f.predicate) &&
            !(event.actor === "board" && ["Audited", "Covered"].includes(f.predicate)),
        );
      }
      this.state.protocolVersion = 2;
    }
    migratePredicateNames(this.state);
    this.state.protocolVersion = 3;
  }
  snapshot() {
    return clone(this.state);
  }
  closure(owner: string) {
    return localClosure(this.state, owner);
  }
  private append(record: InputRecord) {
    putRecord(this.state, record);
  }
  configure(config: PolicyFact[]) {
    const records = config.map((fact) => inputRecord(fact, "config"));
    const next = { stores: clone(this.state.stores) };
    filterRecords(next, (r) => r.source !== "config");
    for (const record of records) putRecord(next, record);
    this.state.stores = next.stores;
  }
  private event(
    kind: RuntimeEvent["kind"],
    msg: Message,
    before: LocalStores,
    check?: PolicyFact[],
    rule?: string,
  ) {
    const after = allRecords(this.state),
      beforeRows = Object.values(before).flat(),
      beforeKeys = new Set(beforeRows.map(recordKey)),
      afterKeys = new Set(after.map(recordKey));
    const seq = ++this.state.revision;
    for (const r of allRecords(this.state)) if (!beforeKeys.has(recordKey(r))) r.event = seq;
    this.state.events.push({
      seq,
      kind,
      message: msg.id,
      actor: kind === "send" ? msg.from : msg.to,
      added: after.filter((r) => !beforeKeys.has(recordKey(r))).map((r) => r.fact),
      removed: beforeRows.filter((r) => !afterKeys.has(recordKey(r))).map((r) => r.fact),
      before,
      after: clone(this.state.stores),
      check,
      rule,
    });
  }
  /** Only this application-owned entrypoint can introduce a trusted source tag. */
  assign(id: string, to: string, tag: string, body: string) {
    this.send("board", to, id, body, { tag });
    return this.settle(id);
  }
  /** Local send runtime computes temporal input facts from successful receive history. */
  send(from: string, to: string, id: string, body: string, trusted?: { tag: string }) {
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
    const before = clone(this.state.stores);
    this.append(inputRecord(f("Sender", from, id), "runtime", from));
    if (trusted) this.append(inputRecord(f("TrustedSource", id, trusted.tag), "trusted app", from));
    // Source assignment is trusted ingestion, not a Board computation over its full history.
    if (!trusted)
      for (const record of before[from]!)
        if (
          record.owner === from &&
          record.fact.predicate === "Received" &&
          record.fact.args[0] === from
        )
          this.append(
            inputRecord(f("ReceivedBeforeSend", record.fact.args[1]!, id), "runtime", from),
          );
    this.append(inputRecord(f("Incoming", to, id), "runtime", to));
    const labels = this.closure(from).facts.filter(
      (fact) =>
        fact.predicate === PROTOCOL.transfers.message.export &&
        fact.args[PROTOCOL.transfers.message.messageArgument] === id,
    );
    const message: Message = { id, from, to, body, labels, status: "pending" };
    this.state.messages.push(message);
    for (const label of labels) {
      const record = inputRecord(
        f(PROTOCOL.transfers.message.import, ...label.args),
        "protocol",
        to,
      );
      record.lifetime = "temporary";
      this.append(record);
    }
    this.event("send", message, before);
    return clone(message);
  }
  /** Gate and delivery use the same Datalog program as all four analyses. */
  settle(id: string) {
    const msg = this.state.messages.find((m) => m.id === id);
    if (msg?.status !== "pending") throw new Error("Select a pending message.");
    const localInput = this.state.stores[msg.to]!;
    if (!localInput.some((r) => factKey(r.fact) === factKey(f("Incoming", msg.to, id))))
      throw new Error(`Missing local receive intent for ${id}; delivery was not attempted.`);
    for (const label of msg.labels)
      if (
        !localInput.some(
          (r) => factKey(r.fact) === factKey(f(PROTOCOL.transfers.message.import, ...label.args)),
        )
      )
        throw new Error(`Incomplete tag envelope for ${id}; delivery was not attempted.`);
    const before = clone(this.state.stores),
      evaluation = this.closure(msg.to),
      denial = f("DenyReceive", msg.to, id);
    const denied = contains(evaluation.facts, denial);
    this.state.stores[msg.to] = this.state.stores[msg.to]!.filter(
      (r) => factKey(r.fact) !== factKey(f("Incoming", msg.to, id)),
    );
    if (!denied) {
      this.append(inputRecord(f("Received", msg.to, id), "runtime", msg.to));
    }
    this.state.stores[msg.to] = this.state.stores[msg.to]!.filter((r) => {
      if (
        r.owner !== msg.to ||
        r.fact.predicate !== PROTOCOL.transfers.message.import ||
        r.fact.args[0] !== id
      )
        return true;
      if (denied) return false;
      r.lifetime = "local";
      return true;
    });
    msg.status = denied ? "denied" : "delivered";
    this.event(
      denied ? "deny" : "receive",
      msg,
      before,
      evaluation.facts,
      denied ? "Soufflé: DenyReceive" : undefined,
    );
    return { allowed: !denied, evaluation, message: clone(msg) };
  }
  accessible(principal: string) {
    return this.state.messages
      .filter((m) => m.from === principal || (m.to === principal && m.status === "delivered"))
      .map(clone);
  }
}

const recordKey = (record: InputRecord) => `${record.owner}:${factKey(record.fact)}`;
/** Upgrade old checkpoints using already recorded envelopes, never a global policy join. */
function migrateRecords(records: InputRecord[], messages: Message[]) {
  const result = clone(records);
  const add = (record: InputRecord) => {
    if (!result.some((r) => recordKey(r) === recordKey(record))) result.push(record);
  };
  for (const message of messages) {
    const pending = records.find(
      (r) => r.fact.predicate === "Incoming" && r.fact.args[1] === message.id,
    );
    const received = records.find(
      (r) =>
        r.fact.predicate === "Received" &&
        r.fact.args[0] === message.to &&
        r.fact.args[1] === message.id,
    );
    if (!pending && !received) continue;
    for (const label of message.labels) {
      const record = inputRecord(
        f(PROTOCOL.transfers.message.import, ...label.args),
        "protocol",
        message.to,
      );
      record.lifetime = received ? "local" : "temporary";
      record.event = received?.event ?? pending?.event;
      add(record);
    }
  }
  return result;
}

const assignments = [
  {
    to: "procurement",
    tag: "nova_procurement",
    id: "mP0",
    body: "Nova: prepare the $8M procurement budget rationale, including the supplier transition.",
  },
  {
    to: "facility",
    tag: "nova_facility",
    id: "mF0",
    body: "Nova: prepare the $3M facilities budget rationale, including the Building 4 consolidation.",
  },
  {
    to: "hr",
    tag: "nova_hiring",
    id: "m0",
    body: "Nova: prepare the $5M hiring budget rationale, including the Team Z hiring plan.",
  },
];
export const REPLIES: Record<string, { tag: string; id: string; body: string }> = {
  procurement: {
    tag: "nova_procurement",
    id: "mP",
    body: "Procurement budget: $8M. Please review the Nova supplier-transition rationale.",
  },
  facility: {
    tag: "nova_facility",
    id: "mF",
    body: "Facility budget: $3M. Please review the Nova Building 4 consolidation rationale.",
  },
  hr: {
    tag: "nova_hiring",
    id: "mH",
    body: "Hiring budget: $5M. Please review the Nova Team Z hiring rationale.",
  },
};
/** Presets schedule actual send/gate/receive calls; they never load event or derived fixtures. */
export function createEpisode(
  preset: "initial" | "earlier" | "denial" = "denial",
  policy?: NovaPolicyArtifact,
) {
  const runtime = new NovaRuntime();
  if (policy) runtime.state.policy = readPolicyArtifact(policy);
  if (preset === "initial") return runtime;
  for (const assignment of assignments)
    runtime.assign(assignment.id, assignment.to, assignment.tag, assignment.body);
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
/** Actual local closures determine ownership; no predicate-specific UI mapping. */
export function view(state: RuntimeState) {
  return {
    ...clone(state),
    records: clone(allRecords(state)), // transient UI/debug projection, absent from checkpoints
    configuration: [
      ...new Map(
        allRecords(state)
          .filter((r) => r.source === "config")
          .map((r) => [factKey(r.fact), r.fact]),
      ).values(),
    ],
    derived: derivedAt(state),
    finished: contains(reconstructDebugView(state).facts, f("Finished", "nova")),
  };
}
