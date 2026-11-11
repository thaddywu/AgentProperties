import { describe, expect, it } from "vitest";
import { PRIMITIVE_MESSAGING_RULES, PRIMITIVES } from "../src/primitives.js";
import { queryDatalog } from "../src/query.js";

describe("readable primitive vocabulary", () => {
  it("derives knowledge only after a real received event and checks declared capabilities", () => {
    const input = [
      { predicate: "ImportedTag", args: ["m", "hiring"] },
      { predicate: "ReceiveAttempt", args: ["reader", "m"] },
      { predicate: "TagRequiresCapability", args: ["hiring", "hr_review"] },
    ];
    expect(queryDatalog(input, PRIMITIVE_MESSAGING_RULES, "?- Knows(A,T).").rows).toEqual([]);
    expect(
      queryDatalog(input, PRIMITIVE_MESSAGING_RULES, "?- Deny(M, message_policy).").rows,
    ).toEqual([["m"]]);
    expect(
      queryDatalog(
        [...input, { predicate: "AgentHasCapability", args: ["reader", "hr_review"] }],
        PRIMITIVE_MESSAGING_RULES,
        "?- Deny(M, message_policy).",
      ).rows,
    ).toEqual([]);
    expect(
      queryDatalog(
        [...input, { predicate: "MessageReceived", args: ["reader", "m"] }],
        PRIMITIVE_MESSAGING_RULES,
        "?- Knows(A,T).",
      ).rows,
    ).toEqual([["reader", "hiring"]]);
    expect(PRIMITIVES.ResourceState.kind).toBe("input");
  });
});
