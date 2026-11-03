import { randomUUID } from "node:crypto";
import type { AgentRunModel, AgentRuntime } from "@rakazo/adapter-kit";

export type PolicyModelUsage = {
  inputTokens: number;
  outputTokens: number;
  provider: string;
  model: string;
};

/** One isolated runtime invocation; callers record the raw text before parsing it. */
export function policyTranslationModel(
  runtime: AgentRuntime,
  model: AgentRunModel,
  signal: AbortSignal,
  instructions: string,
  recordUsage?: (usage: PolicyModelUsage) => void,
) {
  return async (prompt: string, record: (text: string) => void): Promise<string> => {
    const id = randomUUID();
    let text = "";
    try {
      for await (const event of runtime.run(
        {
          botId: "policy-translator",
          threadId: id,
          runId: id,
          instructions,
          prompt,
          history: [],
          tools: [],
          useBuiltinTools: false,
          allowSilentEmpty: true,
          model,
          executeTool: async () => {
            throw new Error("Translation has no tools.");
          },
        },
        { signal, operationId: id, traceId: id },
      )) {
        if (event.type === "usage")
          recordUsage?.({
            inputTokens: event.inputTokens,
            outputTokens: event.outputTokens,
            provider: event.provider,
            model: event.model,
          });
        if (["tool", "subagent", "ask", "takeover"].includes(event.type))
          throw new Error("Unexpected tool or interaction in one-shot translation.");
        if (event.type === "text") {
          text += event.text;
          record(text);
        }
        if (event.type === "done" && event.text !== undefined) {
          text = event.text;
          record(text);
        }
      }
      signal.throwIfAborted();
      return text;
    } catch {
      // Provider errors can contain credentials/URLs. Keep partial raw output, not transport secrets.
      throw new Error(
        "Model invocation failed or timed out; any partial response was preserved. Check the model connection.",
      );
    }
  };
}

export { buildModelConnectPlaintext } from "./model-connect.js";
export { parseModelSecret } from "./pi-oauth.js";
export { PiAgentRuntime } from "./pi-runtime.js";
