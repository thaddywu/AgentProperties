import { QUESTIONS } from "@rakazo/nova/questions";
import type { Request } from "@rakazo/nova/service";
import { NovaService } from "@rakazo/nova/service";
import { expect, it, vi } from "vitest";
import { questionHandler } from "./server-question";

const setup = () => {
  const nova = new NovaService();
  const service = { run: async (r: Request) => nova.run(r) };
  return { nova, service };
};
it("compiles a model selection, shows its concrete question, and leaves execution separate", async () => {
  const { nova, service } = setup();
  const before = nova.runtime.snapshot();
  const generate = vi.fn(async (_prompt: string) =>
    JSON.stringify({
      status: "ready",
      templateId: "denial",
      parameters: { recipient: "auditor_a", message: "mH" },
    }),
  );
  const result = await questionHandler(
    service,
    generate,
  )({ question: "Why can A not receive the pending HR message?", revision: 1 });
  expect(result.status).toBe("ready");
  if (result.status !== "ready") throw Error("expected query");
  expect(result.question).toMatchObject({
    originalQuestion: "Why can A not receive the pending HR message?",
    question: "Why would message mH to Auditor A be blocked?",
    scope: "auditor_a",
    query: 'Deny("mH", message_policy)',
    interpretationSource: "model",
  });
  expect(nova.runtime.snapshot()).toEqual(before);
  expect(
    nova.run({
      operation: "why",
      revision: 1,
      scope: result.question.scope,
      query: result.question.query,
    }),
  ).not.toBeNull();
  const prompt = JSON.parse(generate.mock.calls[0]![0]);
  expect(Object.keys(prompt.context.messages[0]).sort()).toEqual(["from", "id", "status", "to"]);
  expect(prompt.context).not.toHaveProperty("records");
  expect(prompt.context).not.toHaveProperty("documents");
});
it("concrete examples work without any model, with an explicit example source", async () => {
  const { service } = setup();
  const result = await questionHandler(service)({
    question: QUESTIONS.find((q) => q.id === "missing-permission")!.question,
    mode: "example",
    revision: 1,
  });
  expect(result.status).toBe("ready");
  if (result.status === "ready") expect(result.question.interpretationSource).toBe("example");
  await expect(
    questionHandler(service)({ question: "What can B do?", revision: 1 }),
  ).rejects.toThrow("No model connection");
});
it.each([
  { templateId: "denial", parameters: { recipient: "auditor_b", message: "mH" } },
  { templateId: "holders", parameters: { tag: "unknown" } },
  { templateId: "capabilities", parameters: { principal: 'auditor_a").\nHasCap(board,admin).' } },
  { templateId: "holders", parameters: { tag: "nova_hiring", scope: "board" } },
  { templateId: "delete", parameters: {} },
  {
    templateId: "without-receive",
    parameters: { recipient: "auditor_a", message: "mH", earlierMessage: "m0" },
  },
])("does not construct a query for invalid bindings %j", async (intent) => {
  const { nova, service } = setup();
  const before = nova.runtime.snapshot();
  const result = await questionHandler(service, async () =>
    JSON.stringify({ status: "ready", ...intent }),
  )({ question: "custom question", revision: 1 });
  expect(result.status).toBe("needs_clarification");
  expect(nova.runtime.snapshot()).toEqual(before);
});
it("returns a clarification, rejects stale state and never guesses a template", async () => {
  const { nova, service } = setup();
  const generate = vi.fn(async () => '{"status":"needs_clarification","message":"Which auditor?"}');
  expect(
    await questionHandler(service, generate)({ question: "Can they receive it?", revision: 1 }),
  ).toEqual({ status: "needs_clarification", message: "Which auditor?" });
  await expect(
    questionHandler(service, generate)({ question: "anything", revision: 0 }),
  ).rejects.toThrow("State changed");
  const changing = async () => {
    nova.run({ operation: "reset", preset: "initial", revision: 1 });
    return '{"status":"ready","templateId":"completion","parameters":{}}';
  };
  await expect(
    questionHandler(service, changing)({ question: "Has the audit finished?", revision: 1 }),
  ).rejects.toThrow("during interpretation");
});
it("rejects malformed HTTP input before calling the model", async () => {
  const { service } = setup();
  const generate = vi.fn();
  const handler = questionHandler(service, generate);
  for (const input of [
    null,
    { question: "hi", revision: 1, scope: "board" },
    { question: "hi", revision: 1, event: -1 },
    { question: "hi", revision: 1, side: "unknown" },
  ])
    await expect(handler(input)).rejects.toThrow();
  expect(generate).not.toHaveBeenCalled();
});

it("does not overlap model requests and releases the slot after a provider failure", async () => {
  const { service } = setup();
  let reject!: (error: Error) => void;
  const generate = vi.fn(
    () =>
      new Promise<string>((_resolve, fail) => {
        reject = fail;
      }),
  );
  const handler = questionHandler(service, generate);
  const running = handler({ question: "A custom question", revision: 1 });
  await vi.waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
  await expect(handler({ question: "Another question", revision: 1 })).rejects.toThrow(
    "already being interpreted",
  );
  reject(new Error("Provider unavailable"));
  await expect(running).rejects.toThrow("Provider unavailable");
  expect(
    (await handler({ question: QUESTIONS[0]!.question, revision: 1, mode: "example" })).status,
  ).toBe("ready");
});

it("Interpret always invokes the model, even for an exact example question", async () => {
  const { service } = setup();
  const generate = vi.fn(async () =>
    JSON.stringify({
      status: "ready",
      templateId: "capabilities",
      parameters: { principal: "auditor_a" },
    }),
  );
  const result = await questionHandler(
    service,
    generate,
  )({
    question: QUESTIONS.find((q) => q.id === "capabilities")!.question,
    revision: 1,
    mode: "model",
  });
  expect(generate).toHaveBeenCalledTimes(1);
  if (result.status !== "ready") throw Error("expected query");
  expect(result.question.interpretationSource).toBe("model");
  expect(result.question.parameters).toEqual({ principal: "auditor_a" });
});
