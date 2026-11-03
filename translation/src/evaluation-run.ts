import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { ModelConnectInputSchema } from "@rakazo/contracts";
import { novaDocuments } from "@rakazo/nova/documents";
import { connectionGenerator } from "./model.js";
import { translateNovaExtension } from "./nova-extension.js";
import { TRANSLATION_INSTRUCTIONS } from "./prompt.js";

// Real-model pilot; deliberately excluded from ordinary offline tests.
const { values } = parseArgs({
  options: {
    connection: { type: "string" },
    output: { type: "string" },
    trials: { type: "string", default: "3" },
  },
});
if (!values.connection || !values.output)
  throw new Error("Supply --connection <private-connection.json> --output <new-output-directory>.");
const trials = Number(values.trials);
if (!Number.isInteger(trials) || trials < 1 || trials > 5)
  throw new Error("Choose between one and five independent trials.");
const parsedConnection = ModelConnectInputSchema.safeParse(
  JSON.parse(readFileSync(values.connection, "utf8")),
);
if (!parsedConnection.success) throw new Error("Invalid shared model connection.");
const connection = parsedConnection.data;
const output = resolve(values.output);
mkdirSync(output, { mode: 0o700 });
const revision = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
for (let trial = 1; trial <= trials; trial++) {
  const result = await translateNovaExtension({
    documents: novaDocuments(),
    output: resolve(output, `trial-${trial}`),
    metadata: {
      model: connection.modelId,
      provider: connection.provider,
      maxTokens: connection.maxTokens,
      thinkingLevel: connection.thinkingLevel,
      revision,
      trial,
      purpose: "Current-protocol pilot, independent one-shot trials without repair",
    },
    generate: connectionGenerator(connection, TRANSLATION_INSTRUCTIONS),
  });
  console.log(JSON.stringify({ trial, status: result.status, eligible: result.eligible }));
}
