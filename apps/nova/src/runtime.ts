import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import type {
  MessageEvent,
  MessageInputRecord,
  MessageStores,
  MessagingState,
  PolicyMessage,
} from "@rakazo/policy-runtime/messaging";
import { MessagingRuntime } from "@rakazo/policy-runtime/messaging";
import { derivedAt, reconstructDebugView } from "./local-store.js";
import { CONFIG, contains, f, PREDICATES, validateInput } from "./policy.js";
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
import { readPolicyArtifact, rulesFor } from "./translated-policy.js";

export { NAMES, PRINCIPALS } from "./shared.js";
export type InputRecord = MessageInputRecord;
export type Message = PolicyMessage;
export type RuntimeEvent = MessageEvent;
export type LocalStores = MessageStores;
export type RuntimeState = MessagingState<NovaPolicyArtifact> & {
  storeSchemaVersion: 1;
  protocolVersion?: 1 | 2 | 3;
  tagSchemaVersion?: 1;
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
/** Nova supplies its profile and legacy checkpoint migrations; the runtime owns execution. */
export class NovaRuntime extends MessagingRuntime<NovaPolicyArtifact, RuntimeState> {
  constructor(state?: RuntimeState | LegacyRuntimeState) {
    let normalized: RuntimeState;
    const policy =
      state && state.policy !== undefined ? readPolicyArtifact(state.policy) : undefined;
    if (state && "stores" in state)
      normalized = clone({
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
      normalized = {
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
      normalized = {
        storeSchemaVersion: 1,
        protocolVersion: 1,
        tagSchemaVersion: 1,
        stores: emptyStores(),
        messages: [],
        events: [],
        revision: 0,
      };
      for (const fact of CONFIG) putRecord(normalized, inputRecord(fact, "config"));
    }
    // Old summary facts are no longer runtime inputs. Keep messages and gate history.
    if (!normalized.protocolVersion || normalized.protocolVersion < 2) {
      const keep = (r: InputRecord) => r.fact.predicate !== "AuditReceipt";
      filterRecords(normalized, keep);
      for (const event of normalized.events) {
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
      normalized.protocolVersion = 2;
    }
    migratePredicateNames(normalized);
    normalized.protocolVersion = 3;
    super(
      {
        principals: PRINCIPALS,
        sourceAuthorities: ["board"],
        predicates: PREDICATES,
        protocol: PROTOCOL,
        rules: rulesFor(normalized),
        ruleEncoding: normalized.policy ? "parsed" : "raw",
        configuration: CONFIG,
        engine: "souffle",
        roles: {
          sender: "Sender",
          received: "Received",
          incoming: "Incoming",
          order: "ReceivedBeforeSend",
          source: "TrustedSource",
          imported: "TransportTag",
          carries: "MessageTag",
          deny: "DenyReceive",
        },
      },
      normalized,
    );
  }
  assign(id: string, to: string, tag: string, body: string) {
    this.send("board", to, id, body, { tag });
    return this.settle(id);
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
  const runtime = policy
    ? new NovaRuntime({ ...new NovaRuntime().snapshot(), policy: readPolicyArtifact(policy) })
    : new NovaRuntime();
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
