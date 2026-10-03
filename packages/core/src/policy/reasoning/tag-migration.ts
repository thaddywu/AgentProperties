import type { PolicyFact } from "@rakazo/contracts";
import type { InputRecord, LegacyRuntimeState } from "./runtime.js";

// Compatibility only: runtime/rules treat new tags as opaque symbols, never split them.
const legacyTag = (project: string, part: string) =>
  [project, part].map((s) => encodeURIComponent(s).replaceAll("_", "%5F")).join("_");
const fact = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
export function migrateTagSchema(state: LegacyRuntimeState) {
  if (state.tagSchemaVersion === 1) return;
  const memberships = new Map<string, string>();
  const groups = new Set(["nova"]);
  const tag = (project: string, part: string) => {
    const result = legacyTag(project, part);
    groups.add(project);
    memberships.set(result, project);
    return result;
  };
  const convert = (tuple: PolicyFact): PolicyFact => {
    const names: Record<string, string> = {
      TrustedCarry: "TrustedSource",
      TrustedCarries: "TrustedSource",
      Carries: "Propagated",
      Carry: "Propagated",
      TransportCarry: "TransportTag",
    };
    const predicate = names[tuple.predicate] ?? tuple.predicate;
    const a = tuple.args;
    if (
      ["TrustedSource", "Propagated", "TransportTag", "Knows", "AuditReceipt"].includes(
        predicate,
      ) &&
      a.length === 3
    )
      return fact(predicate, a[0]!, tag(a[1]!, a[2]!));
    if (predicate === "Audited" && a.length === 2) return fact(predicate, tag(a[0]!, a[1]!));
    if (predicate === "Requires" && a.length === 3)
      return fact(predicate, tag(a[0]!, a[1]!), a[2]!);
    return { ...tuple, predicate };
  };
  const records = (rows: InputRecord[]) => rows.map((row) => ({ ...row, fact: convert(row.fact) }));
  state.records = records(state.records);
  for (const message of state.messages) message.labels = message.labels.map(convert);
  for (const event of state.events) {
    event.before = records(event.before);
    event.after = records(event.after);
    event.added = event.added.map(convert);
    event.removed = event.removed.map(convert);
    if (event.check) event.check = event.check.map(convert);
  }
  // Old completion required these three components for each project.
  const goals = [...groups].map((group) =>
    fact(
      "AuditGoal",
      group,
      ...["procurement", "facility", "hiring"].map((part) => tag(group, part)),
    ),
  );
  const configuration = [...memberships]
    .map(([t, group]) => fact("TagGroup", t, group))
    .concat(goals);
  const addConfig = (rows: InputRecord[]) => {
    for (const tuple of configuration)
      if (!rows.some((row) => JSON.stringify(row.fact) === JSON.stringify(tuple)))
        rows.push({ fact: tuple, source: "config", owner: "global", lifetime: "global" });
  };
  addConfig(state.records);
  for (const event of state.events) {
    addConfig(event.before);
    addConfig(event.after);
  }
  state.tagSchemaVersion = 1;
}
