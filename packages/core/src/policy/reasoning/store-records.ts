import { factKey } from "../datalog.js";
import { accepts, PROTOCOL } from "./protocol.js";
import type { InputRecord, LocalStores, RuntimeState } from "./runtime.js";
import { PRINCIPALS } from "./shared.js";

export const emptyStores = (): LocalStores => Object.fromEntries(PRINCIPALS.map((p) => [p, []]));
/** Temporary observer projection, never a second writable/persisted store. */
export const allRecords = (state: Pick<RuntimeState, "stores">) =>
  Object.values(state.stores).flat();
export function putRecord(state: Pick<RuntimeState, "stores">, record: InputRecord) {
  const broadcast = record.owner === "*";
  if (broadcast && !PROTOCOL.replicated.some((p) => p === record.fact.predicate))
    throw new Error(`Predicate cannot be replicated: ${record.fact.predicate}`);
  for (const owner of broadcast ? PRINCIPALS : [record.owner]) {
    const store = state.stores[owner];
    if (!store || !accepts(owner, record.fact))
      throw new Error(`Protocol rejects ${record.fact.predicate} at ${owner}`);
    const copy: InputRecord = {
      ...structuredClone(record),
      owner,
      lifetime: record.lifetime === "temporary" ? "temporary" : "local",
      ...(broadcast ? { replicated: true } : {}),
    };
    if (!store.some((r) => factKey(r.fact) === factKey(copy.fact))) store.push(copy);
  }
}
export function filterRecords(
  state: Pick<RuntimeState, "stores">,
  keep: (record: InputRecord) => boolean,
) {
  for (const owner of Object.keys(state.stores))
    state.stores[owner] = state.stores[owner]!.filter(keep);
}
export function partitionLegacyRecords(records: InputRecord[]): LocalStores {
  const state = { stores: emptyStores() };
  for (const record of records)
    putRecord(state, { ...record, owner: record.owner === "global" ? "*" : record.owner });
  return state.stores;
}
