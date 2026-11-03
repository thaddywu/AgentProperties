import { CONFIG } from "../config.js";
import { novaDocuments } from "../documents.js";
import { f, NOVA_RULES } from "../policy.js";
import { closureConformance, comparePrevention } from "../prevention.js";
import { createEpisode } from "../runtime.js";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { createPolicyArtifact, ruleSource } from "../translated-policy.js";

/** Synthetic unsupported remote dependencies, never presented as generated model output. */
export function localityPilot() {
  return ["foreign-negation", "foreign-positive"].map((kind) => {
    const extra =
      kind === "foreign-negation"
        ? 'DenyReceive("auditor_b", M) :- Incoming("auditor_b", M), MessageTag(M, T), Requires(T, C), not HasCap("auditor_a", C).'
        : 'DenyReceive("auditor_b", M) :- Incoming("auditor_b", M), HasReceivedTag("auditor_a", "nova_hiring").';
    let artifact: NovaPolicyArtifact;
    try {
      artifact = createPolicyArtifact(
        novaDocuments(),
        [
          { id: "P1", basis: "builtin", datalog: "", notes: "Unchanged foundation" },
          { id: "P2", basis: "builtin", datalog: "", notes: "Unchanged foundation" },
          {
            id: "P3",
            basis: "extension",
            datalog: `${ruleSource(NOVA_RULES.filter((r) => r.id.startsWith("three-tag")))}\n${extra}`,
            notes:
              "Synthetic locality boundary probe: extra remote dependency, not translation output or a claim about the original P3",
          },
          { id: "P4", basis: "builtin", datalog: "", notes: "Unchanged gate" },
          {
            id: "P5",
            basis: "extension",
            datalog: ruleSource(NOVA_RULES.filter((r) => !r.id.startsWith("three-tag"))),
            notes: "Unchanged coverage",
          },
        ],
        "synthetic locality probe",
      );
    } catch (error) {
      return {
        kind,
        origin: "Handwritten compiler/placement adversarial control, not a model trial",
        rule: extra,
        rejected: true,
        reason: error instanceof Error ? error.message : "Installation rejected",
      };
    }
    const cases = comparePrevention(artifact);
    const runtime = createEpisode("initial", artifact);
    if (kind === "foreign-negation") {
      runtime.configure([...CONFIG, f("HasCap", "auditor_b", "hr_review")]);
      runtime.send("board", "auditor_b", "target", "hiring", { tag: "nova_hiring" });
    } else {
      runtime.assign("prior", "auditor_a", "nova_hiring", "hiring");
      runtime.send("facility", "auditor_b", "target", "ordinary message");
    }
    const conformance = closureConformance(runtime.state);
    const result = runtime.settle("target");
    return {
      kind,
      rejected: false,
      reason: "Unsupported remote dependency was admitted",
      origin: "Handwritten compiler/placement adversarial control, not a model trial",
      rule: extra,
      schemaAccepted: true,
      predefinedCasesPassed: cases.filter(
        (c) => c.matches && c.golden.passed && c.translated?.passed,
      ).length,
      totalPredefinedCases: cases.length,
      localVersusFullCopy: conformance.gates,
      actualAllowed: result.allowed,
      equivalent: conformance.equivalent,
      interpretation:
        "The current protocol does not import the foreign fact. A port needs locality validation or an explicit authorized evidence route; absence in this store is not authoritative foreign absence.",
    };
  });
}
