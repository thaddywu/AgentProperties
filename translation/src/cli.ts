import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { ModelConnectInputSchema } from "@rakazo/contracts";
import { loadRootEnv } from "@rakazo/core/node/load-root-env";
import type { RuntimeBinding } from "@rakazo/policy-runtime/binding";
import { readRuntimeBinding } from "@rakazo/policy-runtime/binding";
import { loadApplication } from "./application.js";
import {
  APPLICATION_TRANSLATION_INSTRUCTIONS,
  translateApplication,
} from "./application-translation.js";
import { connectionGenerator } from "./model.js";

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      connection: { type: "string" },
      binding: { type: "string" },
      "nova-extension": { type: "boolean" },
      provider: { type: "string" },
      model: { type: "string" },
      "api-key-env": { type: "string" },
      "base-url": { type: "string" },
      output: { type: "string" },
      help: { type: "boolean" },
    },
  });
  if (values.help) {
    console.log(
      "From the repository root: pnpm --dir translation translate <app-directory> --connection <private-models-connect.json> [--binding <runtime.json>]\nThe app's runtime.json is used by default. Existing Nova experiments retain their legacy path; --nova-extension generates only app extensions and writes nova-policy.json.\nOr --provider <id> --model <id> --api-key-env <variable> [--base-url <url>]\nOutputs go to this package's ignored output/<binding-id>/<run-id>/; --output overrides it relative to your working directory. The app is not modified.",
    );
    return;
  }
  if (positionals.length !== 1)
    throw new Error(
      "Usage: pnpm --dir translation translate <app-directory> --connection <private-models-connect.json> [--binding <runtime.json>]",
    );
  const directory = resolve(positionals[0]!);
  const documents = await loadApplication(directory);
  const bindingPath = values.binding ? resolve(values.binding) : join(directory, "runtime.json");
  let binding: RuntimeBinding | undefined;
  if (values.binding || existsSync(bindingPath))
    binding = readRuntimeBinding(JSON.parse(readFileSync(bindingPath, "utf8")));
  else if (
    directory !== fileURLToPath(new URL("../../apps/nova/", import.meta.url)).replace(/\/$/, "")
  )
    throw new Error("Provide an adapter-owned runtime.json or --binding for this application.");
  if (
    values["nova-extension"] &&
    (binding ||
      directory !== fileURLToPath(new URL("../../apps/nova/", import.meta.url)).replace(/\/$/, ""))
  )
    throw new Error("--nova-extension requires the Nova application without a generic binding.");
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
  const outputBase = values.output
    ? resolve(values.output)
    : fileURLToPath(new URL(`../output/${binding?.id ?? "nova"}/`, import.meta.url));
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
  const options = {
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
    generate: async (prompt: string, record: (text: string) => void) => {
      if (!connection)
        throw new Error(
          "Missing model configuration. Supply --connection <private-models-connect.json>, or --provider --model --api-key-env [--base-url]. No model was called.",
        );
      return connectionGenerator(
        connection,
        binding
          ? APPLICATION_TRANSLATION_INSTRUCTIONS
          : (await import("./prompt.js")).TRANSLATION_INSTRUCTIONS,
      )(prompt, record);
    },
  };
  const result = values["nova-extension"]
    ? await (await import("./nova-extension.js")).translateNovaExtension(options)
    : binding
      ? await translateApplication({ ...options, binding })
      : await (await import("./experiment.js")).runExperiment(options);
  console.log(`${result.status}\nArtifacts: ${output}`);
  if (
    !["valid_translation_output", "validated_policy_bundle", "validated_nova_extension"].includes(
      String(result.status),
    )
  )
    process.exitCode = 1;
}

main().catch((error: unknown) => {
  // Do not print provider exceptions, connection contents or inherited credentials.
  console.error(
    error instanceof Error && !("code" in error)
      ? error.message
      : "Translation could not start. Install workspace dependencies with pnpm --dir grokbot install --frozen-lockfile and check output permissions; use --help for usage.",
  );
  process.exitCode = 1;
});
