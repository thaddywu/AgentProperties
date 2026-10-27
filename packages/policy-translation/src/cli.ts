import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { ModelConnectInputSchema } from "@rakazo/contracts";
import { loadRootEnv } from "@rakazo/core/node/load-root-env";
import { loadApplication } from "./application.js";
import { runExperiment } from "./experiment.js";
import { TRANSLATION_INSTRUCTIONS } from "./prompt.js";

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      connection: { type: "string" },
      provider: { type: "string" },
      model: { type: "string" },
      "api-key-env": { type: "string" },
      "base-url": { type: "string" },
      output: { type: "string", default: "translation-output/nova" },
      help: { type: "boolean" },
    },
  });
  if (values.help) {
    console.log(
      "pnpm policy:translate examples/nova --connection <private-models-connect.json>\nOr --provider <id> --model <id> --api-key-env <variable> [--base-url <url>]\nOutputs go to ignored translation-output/nova/<run-id>/; the app is not modified.",
    );
    return;
  }
  if (positionals.length !== 1)
    throw new Error(
      "Usage: pnpm policy:translate examples/nova --connection <private-models-connect.json>",
    );
  const documents = await loadApplication(resolve(positionals[0]!));
  loadRootEnv();
  let rawConnection: unknown;
  if (values.connection) {
    try {
      rawConnection = JSON.parse(readFileSync(values.connection, "utf8"));
    } catch {
      throw new Error("Cannot read model connection JSON; use the existing models/connect format.");
    }
  } else {
    const provider = values.provider ?? process.env.PI_DEFAULT_PROVIDER ?? "openrouter";
    rawConnection = {
      provider,
      modelId: values.model ?? process.env.PI_DEFAULT_MODEL,
      apiKey: values["api-key-env"]
        ? process.env[values["api-key-env"]]
        : provider === "openrouter"
          ? process.env.OPENROUTER_API_KEY
          : undefined,
      baseUrl: values["base-url"],
      maxTokens: 8192,
      thinkingLevel: "low",
    };
  }
  const outputBase = resolve(values.output!);
  mkdirSync(outputBase, { recursive: true, mode: 0o700 });
  const output = join(
    outputBase,
    `${new Date().toISOString().replace(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`,
  );
  const parsed = ModelConnectInputSchema.safeParse(rawConnection);
  const connection = parsed.success && parsed.data.modelId?.trim() ? parsed.data : undefined;
  if (!connection)
    console.error(
      "Missing model configuration. Supply --connection <private-models-connect.json> or --provider --model --api-key-env [--base-url]. No model was called.",
    );
  const result = await runExperiment({
    documents,
    output,
    metadata: {
      provider: connection?.provider ?? null,
      model: connection?.modelId ?? null,
      maxTokens: connection?.maxTokens ?? 8192,
      thinkingLevel: connection?.thinkingLevel ?? "low",
      contextWindow: connection?.contextWindow ?? null,
      reasoning: connection?.reasoning ?? null,
      generation:
        "One runtime invocation, no tools or repair; existing runtime transport retry defaults apply.",
      temperature: "runtime default",
      credentialsRecorded: false,
    },
    generate: async (prompt, record) => {
      if (!connection)
        throw new Error(
          "Missing model configuration. Run pnpm policy:translate examples/nova --connection <private-models-connect.json>, or supply --provider --model --api-key-env [--base-url]. No model was called.",
        );
      // Defer the existing provider stack until input/config checks pass; no Prisma/database is required.
      const {
        policyTranslationModel,
        PiAgentRuntime,
        buildModelConnectPlaintext,
        parseModelSecret,
      } = await import("@rakazo/adapters/policy-translation");
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
        AbortSignal.timeout(120_000),
        TRANSLATION_INSTRUCTIONS,
      )(prompt, record);
    },
  });
  console.log(`${result.status}\nArtifacts: ${output}`);
  if (result.status !== "valid_translation_output") process.exitCode = 1;
}

main().catch((error: unknown) => {
  // Do not print provider exceptions, connection contents or inherited credentials.
  console.error(
    error instanceof Error && !("code" in error)
      ? error.message
      : "Translation could not start. Install workspace dependencies with pnpm install --frozen-lockfile and check output permissions; use --help for usage.",
  );
  process.exitCode = 1;
});
