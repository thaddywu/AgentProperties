import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { novaDocuments } from "../src/documents.js";
import { expressivenessPilot } from "../src/evaluation/expressiveness.js";
import { localityPilot } from "../src/evaluation/locality.js";
import { portabilityPilot } from "../src/evaluation/portability.js";
import { recordedPolicy } from "../src/evaluation/recorded-policy.js";
import { translationPilot } from "../src/evaluation/translation.js";
import { configurationPilot } from "../src/evaluation/workflows.js";
import { NOVA_RULES } from "../src/policy.js";
import { comparePrevention } from "../src/prevention.js";
import { createPolicyArtifact, ruleSource } from "../src/translated-policy.js";

describe("research pilot checks and independent counterexamples", () => {
  it("rejects foreign dependencies before installation when the protocol has no evidence route", () => {
    const results = localityPilot();
    expect(results).toHaveLength(2);
    expect(results.every((result) => result.rejected && /remote/.test(result.reason))).toBe(true);
  });

  it("ports a new approval adapter and demonstrates the session and transaction boundaries", async () => {
    const result = await portabilityPilot();
    expect(result.sameSessionProtected).toBe(true);
    expect(result.ordered.concurrent).toEqual([true, false]);
    expect(result.crossSession.sharedExternalPublications).toBe(2);
    expect(result.dualApproval).toEqual({ withOneApproval: false, withTwoApprovals: true });
    expect(result.callbackFailure).toMatchObject({
      failureObserved: true,
      irreversibleEffects: 1,
      committedPublications: 0,
    });
    expect(result.inspection).toMatchObject({
      denialExplained: true,
      hypotheticalUnpublished: true,
      actualStillDenied: true,
    });
  });

  it("distinguishes the executable profile's extension restrictions", () => {
    const result = expressivenessPilot();
    expect(result.compiled.every((probe) => probe.matchedExpectation)).toBe(true);
    expect(result.compiled.find((probe) => probe.id === "four-part-limit")?.accepted).toBe(true);
    expect(result.compiled.find((probe) => probe.id === "helper-relation")?.accepted).toBe(false);
  });

  it("checks the reference against an independent oracle and detects a removed policy guard", () => {
    const reference = translationPilot();
    expect(reference.counts.falseAllows).toBe(0);
    expect(reference.counts.falseDenials).toBe(0);
    expect(reference.counts.coverageMismatches).toBe(0);
    const mutation = createPolicyArtifact(
      novaDocuments(),
      [
        { id: "P1", basis: "builtin", datalog: "", notes: "Unchanged foundation" },
        { id: "P2", basis: "builtin", datalog: "", notes: "Unchanged foundation" },
        {
          id: "P3",
          basis: "builtin",
          datalog: "",
          notes: "Deliberately omitted exposure guard; negative control, not model output",
        },
        { id: "P4", basis: "builtin", datalog: "", notes: "Unchanged gate" },
        {
          id: "P5",
          basis: "extension",
          datalog: ruleSource(
            NOVA_RULES.filter((rule) => ["coverage", "finished"].includes(rule.id)),
          ),
          notes: "Retain coverage",
        },
      ],
      "handwritten mutation control",
    );
    expect(translationPilot(mutation).counts.falseAllows).toBeGreaterThan(0);
  });

  it("reproduces a configuration counterexample that the original installation cases do not detect", () => {
    const artifact = recordedPolicy(
      JSON.parse(
        readFileSync(new URL("../evaluation/model-trials/trial-1.json", import.meta.url), "utf8"),
      ),
    );
    expect(comparePrevention(artifact).every((test) => test.matches)).toBe(true);
    expect(configurationPilot()).toMatchObject({
      deliveries: [true, true, true],
      independentlyComplete: true,
      observerComplete: true,
    });
    expect(configurationPilot(artifact)).toMatchObject({
      deliveries: [true, true, true],
      independentlyComplete: true,
      observerComplete: false,
    });
  });
});
