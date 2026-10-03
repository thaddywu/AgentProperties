import type { PolicyFact, PolicyLabel } from "@rakazo/contracts";
import { describe, expect, it } from "vitest";
import { APP2_RULES, evaluateDatalog } from "./datalog.js";
import { advanceNova, NOVA_PHASES, newNovaSession } from "./nova.js";
import {
  accessibleArtifacts,
  computeArtifact,
  createSource,
  deliverArtifact,
  emptyPolicyState,
} from "./protocol.js";

const carries = (message: string, components: string[], project = "nova"): PolicyFact[] =>
  components.map((component) => ({ predicate: "Carries", args: [message, project, component] }));
const knows = (components: string[], project = "nova"): PolicyFact[] =>
  components.map((component) => ({ predicate: "Knows", args: ["auditor_a", project, component] }));
function deny(known: PolicyFact[], incoming: PolicyFact[]) {
  return evaluateDatalog(
    [...known, ...incoming, { predicate: "Incoming", args: ["auditor_a", "m"] }],
    APP2_RULES,
  ).facts.filter((f) => f.predicate === "Deny");
}
describe("App 2 actual Datalog rules", () => {
  it("denies all three new/known combinations", () => {
    expect(deny([], carries("m", ["p", "f", "h"])).map((f) => f.args[2])).toContain("r3a");
    expect(deny(knows(["p"]), carries("m", ["f", "h"])).map((f) => f.args[2])).toContain("r3b");
    expect(deny(knows(["p", "f"]), carries("m", ["h"])).map((f) => f.args[2])).toContain("r3c");
  });
  it("does not count duplicates or combine different projects", () => {
    expect(deny(knows(["p"]), carries("m", ["p", "p", "f"]))).toEqual([]);
    expect(deny(knows(["p", "f"]), carries("m", ["h"], "other"))).toEqual([]);
    expect(deny(knows(["p", "f"]), carries("another", ["h"]))).toEqual([]);
  });
  it("handles old labels mixed with two new labels and exempts only Board", () => {
    expect(deny(knows(["p"]), carries("m", ["p", "f", "h"]))).toHaveLength(1);
    const input = [
      { predicate: "Incoming", args: ["board", "m"] },
      ...carries("m", ["p", "f", "h"]),
    ];
    expect(evaluateDatalog(input, APP2_RULES).facts.some((f) => f.predicate === "Deny")).toBe(
      false,
    );
  });
  it("derives a transitive computation closure", () => {
    const out = evaluateDatalog(
      [
        ...carries("a", ["p"]),
        { predicate: "DerivedFrom", args: ["c", "b"] },
        { predicate: "DerivedFrom", args: ["b", "a"] },
      ],
      APP2_RULES,
    );
    expect(out.facts).toContainEqual({ predicate: "Carries", args: ["c", "nova", "p"] });
  });
});
describe("App 2 protocol", () => {
  it("prevents unauthorized source labeling and unseen artifact forwarding", () => {
    const state = emptyPolicyState();
    expect(() => createSource(state, "hiring", "a", "secret", [])).toThrow();
    createSource(state, "board", "a", "secret", []);
    expect(() => deliverArtifact(state, "hiring", "auditor_a", "a")).toThrow();
    expect(() => createSource(state, "board", "a", "replacement")).toThrow();
  });
  it("does not commit a denied payload or any candidate facts; retries of known components are safe", () => {
    const state = emptyPolicyState();
    for (const c of ["p", "f", "h"])
      createSource(state, "board", c, `secret-${c}`, [{ project: "nova", component: c }]);
    deliverArtifact(state, "board", "auditor_a", "p");
    deliverArtifact(state, "board", "auditor_a", "f");
    const before = structuredClone(state.local.auditor_a);
    expect(deliverArtifact(state, "board", "auditor_a", "h")).toBe(false);
    expect(state.local.auditor_a).toEqual(before);
    expect(accessibleArtifacts(state, "auditor_a").some((a) => a.text === "secret-h")).toBe(false);
    expect(
      state.local.auditor_a.facts.some((f) => ["Incoming", "New", "Deny"].includes(f.predicate)),
    ).toBe(false);
    expect(deliverArtifact(state, "board", "auditor_a", "p")).toBe(true);
  });
  it("conservatively taints harmless-looking outputs and records exactly the model inputs", async () => {
    const state = emptyPolicyState();
    createSource(state, "board", "reason", "restricted", [{ project: "nova", component: "p" }]);
    deliverArtifact(state, "board", "procurement", "reason");
    let observed: string[] = [];
    await computeArtifact(state, "procurement", "reply", async (inputs) => {
      observed = inputs.map((a) => a.id);
      return { text: "$8M", model: "test" };
    });
    expect(state.artifacts.reply!.inputs).toEqual(observed);
    expect(state.artifacts.reply!.carries).toEqual([{ project: "nova", component: "p" }]);
  });
  it("numbers opposite directions together and keeps historical snapshots immutable", () => {
    const state = emptyPolicyState();
    createSource(state, "board", "a", "public");
    deliverArtifact(state, "board", "procurement", "a");
    deliverArtifact(state, "procurement", "board", "a");
    deliverArtifact(state, "board", "procurement", "a");
    expect(state.events.filter((e) => e.kind === "send").map((e) => e.messageId)).toEqual([
      "msg_board_to_procurement_1",
      "msg_procurement_to_board_2",
      "msg_board_to_procurement_3",
    ]);
    expect(state.events[0]!.after.procurement.artifacts).toEqual([]);
  });
  it("runs the episode through real decisions and never supplies blocked content to the report generator", async () => {
    const state = newNovaSession();
    const captured: string[][] = [];
    for (let i = 0; i < NOVA_PHASES.length; i++)
      await advanceNova(state, async (_owner, _instruction, inputs) => {
        captured.push(inputs.map((a) => a.id));
        return { text: "Generated test response", model: "test" };
      });
    expect(state.status).toBe("blocked");
    expect(state.events.filter((e) => e.decision === "deny").map((e) => e.artifactId)).toEqual([
      "reply_hiring",
    ]);
    expect(captured.at(-1)).not.toContain("reply_hiring");
    expect(state.artifacts.audit_report!.carries).toEqual(
      expect.arrayContaining<PolicyLabel>([
        { project: "nova", component: "procurement" },
        { project: "nova", component: "facility" },
      ]),
    );
    expect(state.events.at(-1)!.decision).toBe("allow");
  });
});
