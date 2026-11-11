import { describe, expect, it } from "vitest";
import { evaluateDatalog } from "../src/datalog.js";
import { MESSAGING_RULES } from "../src/messaging-policy.js";

describe("fixed messaging foundation", () => {
  it("tracks imported information and applies capability requirements without Nova identities", () => {
    const result = evaluateDatalog(
      [
        { predicate: "TransportTag", args: ["input", "medical"] },
        { predicate: "Received", args: ["reader", "input"] },
        { predicate: "Sender", args: ["reader", "reply"] },
        { predicate: "ReceivedBeforeSend", args: ["input", "reply"] },
        { predicate: "Incoming", args: ["reader", "reply"] },
        { predicate: "Requires", args: ["medical", "clearance"] },
      ],
      Object.values(MESSAGING_RULES),
    );
    expect(result.facts).toContainEqual({ predicate: "MessageTag", args: ["reply", "medical"] });
    expect(result.facts).toContainEqual({
      predicate: "HasReceivedTag",
      args: ["reader", "medical"],
    });
    expect(result.facts).toContainEqual({ predicate: "Deny", args: ["reply", "message_policy"] });
  });
  it("does not impose an application exposure threshold or audit goal", () => {
    const result = evaluateDatalog(
      [
        { predicate: "Incoming", args: ["reader", "input"] },
        ...["alpha", "beta", "gamma"].flatMap((tag) => [
          { predicate: "TransportTag", args: ["input", tag] },
          { predicate: "TagGroup", args: [tag, "shared"] },
        ]),
      ],
      Object.values(MESSAGING_RULES),
    );
    expect(result.facts.filter((fact) => fact.predicate === "MessageTag")).toHaveLength(3);
    expect(
      result.facts.some((fact) => ["Deny", "Finished", "HasReceivedTag"].includes(fact.predicate)),
    ).toBe(false);
  });
});
