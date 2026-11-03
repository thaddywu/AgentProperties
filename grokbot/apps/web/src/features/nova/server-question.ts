import {
  compileQuestion,
  exampleIntent,
  QUESTION_ROUTES,
  QUESTION_TEMPLATES,
  QUESTIONS,
} from "@rakazo/nova/questions";
import type { NovaView, Request } from "@rakazo/nova/service";
import { NAMES, PRINCIPALS } from "@rakazo/nova/shared";
import { interpretQuestion } from "@rakazo/policy-translation/question";

/** HTTP composition boundary: interpret outside the native worker, never execute model output. */
export function questionHandler(
  service: { run(request: Request): Promise<unknown> },
  generate?: (prompt: string) => Promise<string>,
) {
  let busy = false;
  return async (body: unknown) => {
    if (busy) throw new Error("A question is already being interpreted. Please wait.");
    if (!body || typeof body !== "object" || Array.isArray(body))
      throw new Error("Invalid question request.");
    const r = body as Record<string, unknown>;
    if (
      Object.keys(r).some((k) => !["question", "revision", "event", "side", "mode"].includes(k)) ||
      typeof r.question !== "string" ||
      !r.question.trim() ||
      r.question.length > 2000 ||
      !Number.isSafeInteger(r.revision) ||
      (r.mode !== undefined &&
        (typeof r.mode !== "string" || !["model", "example"].includes(r.mode))) ||
      (r.event !== undefined && (!Number.isSafeInteger(r.event) || Number(r.event) < 1)) ||
      (r.side !== undefined &&
        (typeof r.side !== "string" || !["before", "after", "check"].includes(r.side)))
    )
      throw new Error("Invalid question or snapshot.");
    const selection = { event: r.event as number | undefined, side: r.side as Request["side"] };
    busy = true;
    try {
      const state = (await service.run({ operation: "state", ...selection })) as NovaView;
      if (state.version !== r.revision)
        throw new Error("State changed. Refresh and interpret again.");
      const context = {
        templates: QUESTION_TEMPLATES,
        routes: QUESTION_ROUTES,
        goalGroups: [
          ...new Set(
            state.configuration.filter((f) => f.predicate === "AuditGoal").map((f) => f.args[0]!),
          ),
        ],
        principals: PRINCIPALS.map((id) => ({ id, name: NAMES[id]! })),
        tags: [
          ...new Set(
            state.records.flatMap((record) =>
              ["TagGroup", "Requires"].includes(record.fact.predicate)
                ? [record.fact.args[0]!]
                : ["TrustedSource", "TransportTag"].includes(record.fact.predicate)
                  ? [record.fact.args[1]!]
                  : [],
            ),
          ),
        ],
        messages: state.messages.map(({ id, from, to, status }) => ({ id, from, to, status })),
        snapshot: selection.event
          ? `Event ${selection.event}, ${selection.side ?? "after"}`
          : "Current runtime",
      };
      const example =
        r.mode === "example"
          ? QUESTIONS.find(
              (q) => q.question.toLowerCase() === String(r.question).trim().toLowerCase(),
            )
          : undefined;
      if (r.mode === "example" && !example) throw new Error("Unknown offline example.");
      if (!example && !generate)
        throw new Error(
          "No model connection configured. Choose an example, or configure MODEL_CONNECTION_FILE on the server.",
        );
      const intent = example
        ? { status: "ready" as const, ...exampleIntent(example.id) }
        : await interpretQuestion(r.question, context, generate!);
      const current = (await service.run({ operation: "state" })) as NovaView;
      if (current.version !== r.revision)
        throw new Error("State changed during interpretation. Refresh and ask again.");
      if (intent.status !== "ready") return intent;
      try {
        const question = compileQuestion(intent.templateId, intent.parameters, context);
        return {
          status: "ready" as const,
          question: {
            ...question,
            originalQuestion: r.question,
            interpretationSource: example ? "example" : "model",
          },
          revision: state.version,
          selection,
        };
      } catch (error) {
        return {
          status: "needs_clarification" as const,
          message: error instanceof Error ? error.message : "Select a supported question.",
        };
      }
    } finally {
      busy = false;
    }
  };
}
