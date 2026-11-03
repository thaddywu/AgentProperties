import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import type { InputRecord, LegacyRuntimeState, LocalStores, RuntimeState } from "./runtime.js";

// Compatibility only. Current rules and inputs accept only the new vocabulary.
const names: Record<string, string> = {
  Propagated: "MessageTag",
  Knows: "HasReceivedTag",
  Audited: "Covered",
  Before: "ReceivedBeforeSend",
  DependsOn: "MayDependOn",
};
export function migratePredicateNames(state: RuntimeState | LegacyRuntimeState) {
  if (state.protocolVersion === 3) return;
  const convert = (fact: PolicyFact): PolicyFact => ({
    ...fact,
    predicate: names[fact.predicate] ?? fact.predicate,
  });
  // Received was already the canonical delivery record. Do not invent a successful
  // receipt from an orphan Receiver tuple in an incomplete historical snapshot.
  const facts = (rows: PolicyFact[]) => [
    ...new Map(
      rows
        .filter((f) => f.predicate !== "Receiver")
        .map(convert)
        .map((f) => [factKey(f), f]),
    ).values(),
  ];
  const records = (rows: InputRecord[]) =>
    rows
      .filter((r) => r.fact.predicate !== "Receiver")
      .map((r) => ({ ...r, fact: convert(r.fact) }));
  const stores = (value: LocalStores) =>
    Object.fromEntries(Object.entries(value).map(([owner, rows]) => [owner, records(rows)]));
  if ("stores" in state) {
    state.stores = stores(state.stores);
    for (const event of state.events) {
      event.before = stores(event.before);
      event.after = stores(event.after);
    }
  } else {
    state.records = records(state.records);
    for (const event of state.events) {
      event.before = records(event.before);
      event.after = records(event.after);
    }
  }
  for (const message of state.messages) message.labels = facts(message.labels);
  for (const event of state.events) {
    event.added = facts(event.added);
    event.removed = facts(event.removed);
    if (event.check) event.check = facts(event.check);
    if (event.rule)
      event.rule = event.rule.replace(
        /\b(Propagated|Knows|Audited|Before|DependsOn|Receiver)\b/g,
        (name) => (name === "Receiver" ? "Received" : names[name]!),
      );
  }
}
