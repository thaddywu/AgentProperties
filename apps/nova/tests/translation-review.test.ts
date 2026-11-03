import { describe, expect, it } from "vitest";
import { NOVA_PROTOCOL, PROTOCOL } from "../src/protocol.js";
import { NovaService } from "../src/service.js";
import { policyCorrespondence, savedTranslationReview } from "../src/translation-review.js";

describe("saved translation demo", () => {
  it("maps exact source paragraphs to current reference rules without rewriting model output", () => {
    const artifact = savedTranslationReview().artifact;
    expect(artifact.id).toBe("5f15c1a29882a59d9ea0a7049987bcf5f50e10f3ec4fd731f2ee65383042b685");
    const rows = policyCorrespondence(artifact);
    expect(rows.map((row) => row.id)).toEqual(["P1", "P2", "P3", "P4", "P5"]);
    expect(rows[2]!.inputMatchesReference).toBe(true);
    expect(rows[2]!.source).toContain("P3. No agent other than Board");
    expect(rows[2]!.ruleIds).toHaveLength(3);
    expect(rows[2]!.generated).toBe(artifact.policies[2]!.datalog);
    expect(rows[4]!.golden).not.toContain("AuditReceipt");
    expect(savedTranslationReview().correspondence[4]!.golden).toContain("AuditReceipt");
    expect(rows[4]!.generated).not.toContain("Audited(Tag) :- AuditReceipt(A, Tag).");
    expect(rows[3]!.protocol).toContain("release no payload");
    const changed = structuredClone(artifact);
    changed.documents.find((doc) => doc.path === "policy.md")!.content = changed.documents
      .find((doc) => doc.path === "policy.md")!
      .content.replace("P3. No agent", "P3. Another agent");
    expect(policyCorrespondence(changed)[2]!.inputMatchesReference).toBe(false);
  });
  it("displays the historical failed translation and preserves the active session", () => {
    const service = new NovaService();
    const before = service.runtime.snapshot();
    const review = service.run({ operation: "replay-translation", revision: 1 }) as {
      replay: boolean;
      modelCalled: boolean;
      eligible: boolean;
      cases: {
        matches: boolean;
        difference: {
          missingFacts: string[];
          decisionsChanged: boolean;
          visibilityChanged: boolean;
        };
      }[];
    };
    expect(review.replay).toBe(true);
    expect(review.modelCalled).toBe(false);
    expect(review.eligible).toBe(false);
    expect(review.cases.filter((test) => test.matches)).toHaveLength(7);
    expect(review.cases.at(-1)!.difference).toMatchObject({
      decisionsChanged: false,
      visibilityChanged: false,
    });
    expect(review.cases.at(-1)!.difference.missingFacts).toHaveLength(3);
    expect(service.runtime.snapshot()).toEqual(before);
    expect(service.version).toBe(1);
  });
  it("shows app protocol additions without duplicating builtin transport", () => {
    expect(NOVA_PROTOCOL.observer).toEqual(PROTOCOL.observer);
    expect(PROTOCOL.transfers).not.toHaveProperty("audit");
    expect(NOVA_PROTOCOL.replicated).toEqual(["Auditor", "AuditGoal"]);
    expect(NOVA_PROTOCOL.local).not.toHaveProperty("Received");
    expect(NOVA_PROTOCOL.local).toHaveProperty("Covered");
  });
});
