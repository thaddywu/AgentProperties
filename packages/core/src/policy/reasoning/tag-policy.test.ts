import type { PolicyFact } from "@rakazo/contracts";
import { describe, expect, it } from "vitest";
import { legacyCheckpoint } from "./legacy-checkpoint.fixture.js";
import { contains, evaluate, f } from "./policy.js";
import { createEpisode, NovaRuntime } from "./runtime.js";
import { allRecords } from "./store-records.js";

const group = [f("TagGroup", "red", "g"), f("TagGroup", "blue", "g"), f("TagGroup", "green", "g")];
const deny = (facts: PolicyFact[], actor = "auditor_a") =>
  contains(evaluate(facts).facts, f("DenyReceive", actor, "incoming"));
const twoKnown = [
  f("Received", "auditor_a", "one"),
  f("TransportTag", "one", "red"),
  f("Received", "auditor_a", "two"),
  f("TransportTag", "two", "blue"),
  f("Incoming", "auditor_a", "incoming"),
];

describe("opaque taint tags and grouped exposure", () => {
  it("denies three distinct tags from the same group without parsing tag names", () => {
    expect(deny([...group, ...twoKnown, f("TransportTag", "incoming", "green")])).toBe(true);
  });
  it("does not combine tags from unrelated groups", () => {
    expect(
      deny([
        ...group.filter((f) => f.args[0] !== "green"),
        f("TagGroup", "green", "other"),
        ...twoKnown,
        f("TransportTag", "incoming", "green"),
      ]),
    ).toBe(false);
  });
  it("counts distinct tags, not repeated copies of the same tag", () => {
    expect(deny([...group, ...twoKnown, f("TransportTag", "incoming", "blue")])).toBe(false);
  });
  it("handles two incoming tags plus one known and all three incoming tags", () => {
    const incoming = [
      f("Incoming", "auditor_a", "incoming"),
      f("TransportTag", "incoming", "blue"),
      f("TransportTag", "incoming", "green"),
    ];
    expect(
      deny([
        ...group,
        ...incoming,
        f("Received", "auditor_a", "one"),
        f("TransportTag", "one", "red"),
      ]),
    ).toBe(true);
    expect(deny([...group, ...incoming, f("TransportTag", "incoming", "red")])).toBe(true);
    expect(
      deny(
        [
          ...group,
          f("Incoming", "board", "incoming"),
          ...["red", "blue", "green"].map((tag) => f("TransportTag", "incoming", tag)),
        ],
        "board",
      ),
    ).toBe(false);
  });
  it("uses configured tags for completion, not fixed part names", () => {
    const facts = [
      f("AuditGoal", "goal", "red", "blue", "green"),
      f("AuditReceipt", "auditor_a", "red"),
      f("AuditReceipt", "auditor_b", "blue"),
    ];
    expect(evaluate(facts).facts).not.toContainEqual(f("Finished", "goal"));
    expect(evaluate([...facts, f("AuditReceipt", "auditor_a", "green")]).facts).toContainEqual(
      f("Finished", "goal"),
    );
  });
  it("migrates old facts, message tags and historical snapshots without resetting the episode", () => {
    const current = createEpisode().snapshot();
    const old = legacyCheckpoint(current);
    delete old.tagSchemaVersion;
    const legacy = (tuple: PolicyFact): PolicyFact => {
      const names: Record<string, string> = {
        TrustedSource: "TrustedCarry",
        Propagated: "Carries",
        TransportTag: "TransportCarry",
      };
      const predicate = names[tuple.predicate] ?? tuple.predicate;
      if (
        ["TrustedSource", "Propagated", "TransportTag", "Knows", "AuditReceipt"].includes(
          tuple.predicate,
        )
      )
        return f(predicate, tuple.args[0]!, "nova", tuple.args[1]!.slice(5));
      if (predicate === "Audited") return f(predicate, "nova", tuple.args[0]!.slice(5));
      if (predicate === "Requires")
        return f(predicate, "nova", tuple.args[0]!.slice(5), tuple.args[1]!);
      return tuple;
    };
    const isOld = (tuple: PolicyFact) => !["TagGroup", "AuditGoal"].includes(tuple.predicate);
    old.records = old.records
      .filter((r) => isOld(r.fact))
      .map((r) => ({ ...r, fact: legacy(r.fact) }));
    for (const message of old.messages) message.labels = message.labels.map(legacy);
    for (const event of old.events) {
      event.before = event.before
        .filter((r) => isOld(r.fact))
        .map((r) => ({ ...r, fact: legacy(r.fact) }));
      event.after = event.after
        .filter((r) => isOld(r.fact))
        .map((r) => ({ ...r, fact: legacy(r.fact) }));
      event.added = event.added.map(legacy);
      event.removed = event.removed.map(legacy);
      event.check = event.check?.map(legacy);
    }
    const migrated = new NovaRuntime(old);
    expect(migrated.state.messages).toEqual(current.messages);
    expect(migrated.state.revision).toBe(current.revision);
    const sortedFacts = (facts: PolicyFact[]) => facts.map((f) => JSON.stringify(f)).sort();
    expect(sortedFacts(allRecords(migrated.state).map((r) => r.fact))).toEqual(
      sortedFacts(allRecords(current).map((r) => r.fact)),
    );
    for (let i = 0; i < current.events.length; i++) {
      expect(
        sortedFacts(
          Object.values(migrated.state.events[i]!.before)
            .flat()
            .map((r) => r.fact),
        ),
      ).toEqual(
        sortedFacts(
          Object.values(current.events[i]!.before)
            .flat()
            .map((r) => r.fact),
        ),
      );
      expect(
        sortedFacts(
          Object.values(migrated.state.events[i]!.after)
            .flat()
            .map((r) => r.fact),
        ),
      ).toEqual(
        sortedFacts(
          Object.values(current.events[i]!.after)
            .flat()
            .map((r) => r.fact),
        ),
      );
    }
    expect(migrated.closure("auditor_a").facts).toContainEqual(f("DenyReceive", "auditor_a", "mH"));
    expect(new NovaRuntime(migrated.snapshot()).state).toEqual(migrated.state);
  });
});
