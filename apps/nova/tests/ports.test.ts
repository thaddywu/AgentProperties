import { describe, expect, it } from "vitest";
import { novaBackendTrial, novaReportFsmTrial } from "../src/port-demo.js";

describe("Nova through the public backend port", () => {
  it("uses canonical primitives, enforces actual releases and completes a split audit", async () => {
    const result = await novaBackendTrial();
    expect(result).toMatchObject({
      deniedMissingCapability: true,
      deniedBodyReleased: false,
      hiringDeliveredToAuthorizedAuditor: true,
      auditComplete: true,
    });
    expect(result.auditorAKnows).toEqual(["nova_hiring", "nova_procurement"]);
  });
  it("materializes authorized observer evidence into a real protected report FSM", async () => {
    expect(await novaReportFsmTrial(false)).toMatchObject({
      approved: false,
      published: false,
      callbacks: 0,
      currentState: [["draft"]],
      committedActions: 0,
    });
    expect(await novaReportFsmTrial(true)).toMatchObject({
      prematurePublishDenied: true,
      approved: true,
      published: true,
      callbacks: 2,
      currentState: [["published"]],
      committedActions: 2,
    });
  });
});
