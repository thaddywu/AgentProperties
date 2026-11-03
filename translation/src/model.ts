import { ModelConnectInputSchema } from "@rakazo/contracts";

/** Reuse the existing models/connect contract and provider adapter. Credentials stay server-side. */
export function connectionGenerator(raw: unknown, instructions: string, timeoutMs = 120_000) {
  const parsed = ModelConnectInputSchema.safeParse(raw);
  if (!parsed.success || !parsed.data.modelId?.trim()) throw new Error("Invalid model connection.");
  const connection = parsed.data;
  return async (prompt: string, record: (text: string) => void = () => {}) => {
    const { policyTranslationModel, PiAgentRuntime, buildModelConnectPlaintext, parseModelSecret } =
      await import("@rakazo/adapters/policy-translation");
    const secret = parseModelSecret(buildModelConnectPlaintext(connection));
    const model = {
      provider: connection.provider,
      id: connection.modelId!,
      maxTokens: connection.maxTokens ?? 8192,
      thinkingLevel: connection.thinkingLevel ?? "low",
      contextWindow: connection.contextWindow,
      ...(secret.kind === "api_key"
        ? { apiKey: secret.key }
        : secret.kind === "openai_compatible"
          ? { apiKey: secret.apiKey, baseUrl: secret.baseUrl, reasoning: secret.reasoning }
          : {}),
    };
    return policyTranslationModel(
      new PiAgentRuntime(),
      model,
      AbortSignal.timeout(timeoutMs),
      instructions,
    )(prompt, record);
  };
}
