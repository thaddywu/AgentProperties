import { expect, it, vi } from "vitest";
import { interpretQuestion, parseQuestionIntent } from "./question.js";

it("uses one injected generation and accepts only a structured intent", async () => {
  const generate = vi.fn(
    async (_prompt: string) =>
      '{"status":"ready","templateId":"holders","parameters":{"tag":"nova_hiring"}}',
  );
  const context = {
    templates: [],
    principals: [],
    tags: ["nova_hiring"],
    messages: [],
    snapshot: "Current runtime",
  };
  expect(await interpretQuestion("谁收到了 HR 的信息？", context, generate)).toEqual({
    status: "ready",
    templateId: "holders",
    parameters: { tag: "nova_hiring" },
  });
  expect(generate).toHaveBeenCalledTimes(1);
  expect(JSON.parse(generate.mock.calls[0]![0])).toEqual({
    question: "谁收到了 HR 的信息？",
    context,
  });
});
it.each([
  "null",
  "[]",
  "```json\n{}\n```",
  '{"status":"ready","templateId":"holders","parameters":[],"query":"evil"}',
  '{"status":"ready","templateId":"holders","parameters":{"tag":1}}',
  '{"status":"ready","templateId":"holders","parameters":{},"scope":"board"}',
  '{"status":"needs_clarification","message":"","parameters":{}}',
])("rejects malformed or executable model output %s", (raw) =>
  expect(() => parseQuestionIntent(raw)).toThrow(),
);
it("preserves clarification and unsupported responses without executing", () => {
  expect(
    parseQuestionIntent('{"status":"needs_clarification","message":"Which message?"}'),
  ).toEqual({ status: "needs_clarification", message: "Which message?" });
  expect(
    parseQuestionIntent('{"status":"unsupported","message":"This would change permissions."}')
      .status,
  ).toBe("unsupported");
});
it("rejects oversized input before calling the provider", async () => {
  const generate = vi.fn();
  await expect(
    interpretQuestion(
      "x".repeat(2001),
      { templates: [], principals: [], tags: [], messages: [], snapshot: "" },
      generate,
    ),
  ).rejects.toThrow();
  expect(generate).not.toHaveBeenCalled();
});

it("accepts bounded identifier lists but rejects executable or nested argument objects", () => {
  expect(
    parseQuestionIntent(
      JSON.stringify({
        status: "ready",
        templateId: "planning",
        parameters: { goalGroup: "nova", basis: "earlier", routes: ["hr->auditor_a"] },
      }),
    ),
  ).toMatchObject({ parameters: { routes: ["hr->auditor_a"] } });
  for (const routes of [[{ code: "something" }], Array(13).fill("hr->auditor_a"), [1]])
    expect(() =>
      parseQuestionIntent(
        JSON.stringify({ status: "ready", templateId: "planning", parameters: { routes } }),
      ),
    ).toThrow();
});
