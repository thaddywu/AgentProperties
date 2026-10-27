import type { PolicyFact } from "@rakazo/contracts";
import { CONFIG } from "@rakazo/nova/config";
import { REASONING_RULES } from "@rakazo/nova/policy";
import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { parseDatalog } from "./validation.js";

// Imported only AFTER generation. These are local-store probes, not runtime integration.
export function compareGenerated(source: string) {
  const { rules, facts } = parseDatalog(source);
  const extra = facts.map((fact) => ({ ...fact, args: fact.args.map((arg) => arg.slice(2)) }));
  const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
  const tags = ["nova_procurement", "nova_facility", "nova_hiring"];
  const observables = new Set(["Propagated", "Knows", "DenyReceive", "Audited", "Finished"]);
  const keys = (input: PolicyFact[]) =>
    new Set(
      input
        .filter((fact) => observables.has(fact.predicate))
        .map((fact) => JSON.stringify([fact.predicate, ...fact.args])),
    );
  const cases: { name: string; input: PolicyFact[] }[] = [];
  for (const [name, owner, known, incoming] of [
    ["ordinary-public-message", "auditor_a", [], []],
    ["hr-capability-present", "auditor_a", [], [tags[2]]],
    ["hr-capability-absent", "auditor_b", [], [tags[2]]],
    ["third-part", "auditor_a", tags.slice(0, 2), tags.slice(2)],
    ["two-incoming", "auditor_a", tags.slice(0, 1), tags.slice(1)],
    ["all-incoming", "auditor_a", [], tags],
    ["duplicate-tag", "auditor_a", tags.slice(0, 1), tags.slice(0, 1)],
    ["different-groups", "auditor_a", tags.slice(0, 2), ["unrelated"]],
    ["board-exposure-exemption", "board", tags.slice(0, 2), tags.slice(2)],
  ] as [string, string, string[], string[]][]) {
    const input = CONFIG.filter((fact) => fact.predicate !== "HasCap" || fact.args[0] === owner);
    if (name === "different-groups") input.push(f("TagGroup", "unrelated", "other"));
    if (owner === "board") input.push(f("HasCap", owner, "hr_review"));
    known.forEach((tag, index) => {
      input.push(
        f("Receiver", owner, `old${index}`),
        f("Received", owner, `old${index}`),
        f("TransportTag", `old${index}`, tag),
      );
    });
    input.push(
      f("Incoming", owner, "candidate"),
      ...incoming.map((tag) => f("TransportTag", "candidate", tag)),
    );
    cases.push({ name, input });
  }
  cases.push(
    {
      name: "board-capability-not-exempt",
      input: [
        ...CONFIG.filter((fact) => fact.predicate !== "HasCap"),
        f("Incoming", "board", "candidate"),
        f("TransportTag", "candidate", tags[2]!),
      ],
    },
    {
      name: "successful-receipt-lineage",
      input: [
        f("Receiver", "facility", "old"),
        f("Received", "facility", "old"),
        f("TransportTag", "old", tags[1]!),
        f("Sender", "facility", "out"),
        f("Before", "old", "out"),
      ],
    },
    {
      name: "attempt-is-not-receipt",
      input: [
        f("Incoming", "facility", "old"),
        f("TransportTag", "old", tags[1]!),
        f("Sender", "facility", "out"),
      ],
    },
    {
      name: "board-source-ingestion",
      input: [f("Sender", "board", "assignment"), f("TrustedSource", "assignment", tags[0]!)],
    },
    {
      name: "board-audit-coverage",
      input: [
        ...CONFIG.filter((fact) => fact.predicate !== "HasCap"),
        ...tags.map((tag, i) => f("AuditReceipt", i === 1 ? "auditor_b" : "auditor_a", tag)),
      ],
    },
  );
  return cases.map(({ name, input }) => {
    const reference = keys(runSouffle(input, REASONING_RULES).facts);
    const generated = keys(runSouffle([...input, ...extra], rules).facts);
    const missing = [...reference].filter((key) => !generated.has(key));
    const unexpected = [...generated].filter((key) => !reference.has(key));
    return { name, passed: !missing.length && !unexpected.length, missing, unexpected };
  });
}
