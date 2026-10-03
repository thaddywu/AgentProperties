import { factKey } from "../datalog.js";
import type { InputRecord, LegacyRuntimeState, LocalStores, RuntimeState } from "./runtime.js";

/** Test fixture for the pre-partition checkpoint format. */
export function legacyCheckpoint(state: RuntimeState): LegacyRuntimeState {
  const rows = (stores: LocalStores) => {
    const unique = new Map<string, InputRecord>();
    for (const r of Object.values(stores).flat()) {
      const { replicated, ...record } = structuredClone(r);
      if (replicated) {
        record.owner = "global";
        record.lifetime = "global";
      }
      unique.set(`${record.owner}:${factKey(record.fact)}`, record);
    }
    return [...unique.values()];
  };
  const { stores, storeSchemaVersion: _, events, ...rest } = structuredClone(state);
  return {
    ...rest,
    records: rows(stores),
    events: events.map((event) => ({
      ...event,
      before: rows(event.before),
      after: rows(event.after),
    })),
  };
}
