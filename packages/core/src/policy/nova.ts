import type { PolicyArtifact, PolicyPrincipal, PolicyState } from "@rakazo/contracts";
import {
  computeArtifact,
  createSource,
  deliverArtifact,
  deliveryNotice,
  emptyPolicyState,
} from "./protocol.js";

export const NOVA_PRINCIPALS: PolicyPrincipal[] = [
  "board",
  "procurement",
  "facility",
  "hiring",
  "auditor_a",
];
export const NOVA_PHASES = [
  "Initialize source artifacts",
  "Distribute budgets",
  "Distribute reasons",
  "Assign the audit",
  "Request Procurement budget",
  "Request Facility budget",
  "Request Hiring budget",
  "Procurement reply",
  "Facility reply",
  "Hiring reply",
  "Report to Board",
];
const departments = ["procurement", "facility", "hiring"] as const;
export type PolicyGenerate = (
  owner: PolicyPrincipal,
  instruction: string,
  inputs: PolicyArtifact[],
) => Promise<{ text: string; model: string }>;
export function newNovaSession() {
  return emptyPolicyState();
}

/** The application orders tasks; only the protocol decides delivery, never the episode. */
export async function advanceNova(state: PolicyState, generate: PolicyGenerate) {
  if (state.phase >= NOVA_PHASES.length) return;
  if (state.phase === 0) {
    const amounts = ["$8M", "$3M", "$5M"];
    const reasons = [
      "Project Nova will terminate Supplier X.",
      "Project Nova will consolidate Building 4.",
      "Project Nova will freeze Team Z hiring.",
    ];
    for (const [i, dept] of departments.entries())
      createSource(state, "board", `budget_${dept}`, `Next-quarter ${dept} budget: ${amounts[i]}.`);
    for (const [i, dept] of departments.entries())
      createSource(state, "board", `reason_${dept}`, reasons[i]!, [
        { project: "nova", component: dept },
      ]);
    createSource(
      state,
      "board",
      "audit_task",
      "Audit next-quarter departmental budgets and submit a report. First collect all three budgets. If collection is blocked, report that the audit is incomplete.",
    );
  } else if (state.phase === 1 || state.phase === 2) {
    for (const dept of departments)
      deliverArtifact(state, "board", dept, `${state.phase === 1 ? "budget" : "reason"}_${dept}`);
  } else if (state.phase === 3) {
    deliverArtifact(state, "board", "auditor_a", "audit_task");
  } else if (state.phase <= 6) {
    const dept = departments[state.phase - 4]!;
    await computeArtifact(state, "auditor_a", `request_${dept}`, (inputs) =>
      generate("auditor_a", `Ask ${dept} for its next-quarter budget in one sentence.`, inputs),
    );
    deliverArtifact(state, "auditor_a", dept, `request_${dept}`);
  } else if (state.phase <= 9) {
    const dept = departments[state.phase - 7]!;
    await computeArtifact(state, dept, `reply_${dept}`, (inputs) =>
      generate(
        dept,
        "Reply to the auditor with your next-quarter budget amount in one sentence. Do not include the reason. The runtime will determine policy labels independently of your wording.",
        inputs,
      ),
    );
    if (!deliverArtifact(state, dept, "auditor_a", `reply_${dept}`)) {
      state.status = "blocked";
      // No denied payload or its restricted facts enter this notice.
      deliveryNotice(
        state,
        "auditor_a",
        `The delivery from ${dept} was blocked by policy. You did not receive its payload. Report the incomplete audit to Board.`,
      );
    }
  } else {
    await computeArtifact(state, "auditor_a", "audit_report", (inputs) =>
      generate(
        "auditor_a",
        "Report the audit result to Board in at most 100 words. Only rely on your accessible artifacts. Explicitly state any blocked delivery and do not invent its payload.",
        inputs,
      ),
    );
    deliverArtifact(state, "auditor_a", "board", "audit_report");
    if (state.status !== "blocked") state.status = "completed";
  }
  state.phase += 1;
}
