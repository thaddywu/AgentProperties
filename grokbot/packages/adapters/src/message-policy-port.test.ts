import { createMessagingProfile } from "@rakazo/policy-runtime/messaging";
import { describe, expect, it, vi } from "vitest";
import { createGrokbotMessagePort } from "./message-policy-port.js";

describe("Grokbot message policy adapter", () => {
  it("maps authenticated run identities into the shared runtime before releasing the message", async () => {
    const profile = createMessagingProfile({
      principals: ["source", "sender", "auditor"],
      sourceAuthorities: ["source"],
      configuration: [
        { predicate: "TagRequiresCapability", args: ["secret", "review"] },
        { predicate: "AgentHasCapability", args: ["sender", "review"] },
      ],
    });
    const deliver = vi.fn(async () => {});
    const port = createGrokbotMessagePort({
      spaceId: "space",
      userId: "owner",
      principalByBot: { source_bot: "source", sender_bot: "sender", auditor_bot: "auditor" },
      profile,
      deliver,
    });
    await port.ingest({
      authority: "source",
      recipient: "sender",
      id: "seed",
      body: "synthetic report",
      tag: "secret",
    });
    const run = { id: "run", spaceId: "space", userId: "owner", botId: "sender_bot" };
    const denied = await port.forRun(run).send({
      recipientBotId: "auditor_bot",
      deliveryKey: "tool_call_1",
      message: "rewritten report",
    });
    expect(denied.allowed).toBe(false);
    expect(deliver).toHaveBeenCalledTimes(1);
    expect(port.snapshot().messages.at(-1)).toMatchObject({
      from: "sender",
      to: "auditor",
      id: "run:tool_call_1",
      status: "denied",
    });
    expect(() => port.forRun({ ...run, userId: "other" })).toThrow(/authenticated scope/);
    expect(() =>
      port.forRun(run).send({ recipientBotId: "unknown", deliveryKey: "key", message: "plain" }),
    ).toThrow(/registered recipient/);
  });
});
