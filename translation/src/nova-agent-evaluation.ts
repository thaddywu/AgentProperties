import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { ModelConnectInputSchema } from "@rakazo/contracts";
import {
  createRoutingEpisode,
  InvalidRouteError,
  parseRoutes,
  ROUTING_CASES,
  ROUTING_INSTRUCTIONS,
} from "@rakazo/nova/evaluation/routing-agent";
import { readPolicyArtifact } from "@rakazo/nova/translated-policy";
import { connectionGenerator } from "./model.js";

// Explicit real-model experiment, excluded from routine offline test execution.
const { values } = parseArgs({
  options: {
    connection: { type: "string" },
    output: { type: "string" },
    artifact: { type: "string" },
    trials: { type: "string", default: "1" },
  },
});
if (!values.connection || !values.output)
  throw new Error("Supply a private --connection and a new --output directory.");
const trials = Number(values.trials);
if (!Number.isInteger(trials) || trials < 1 || trials > 5)
  throw new Error("Choose one to five repetitions.");
const parsedConnection = ModelConnectInputSchema.safeParse(
  JSON.parse(readFileSync(values.connection, "utf8")),
);
if (!parsedConnection.success) throw new Error("Invalid shared model connection.");
const connection = parsedConnection.data;
const policy = values.artifact
  ? readPolicyArtifact(JSON.parse(readFileSync(values.artifact, "utf8")))
  : undefined;
const output = resolve(values.output);
mkdirSync(output, { mode: 0o700 });
const save = (file: string, value: unknown) =>
  writeFileSync(resolve(output, file), `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
const episodes = [];
for (let repeat = 0; repeat < trials; repeat++)
  for (const scenario of ROUTING_CASES) {
    const conditions: ("disabled" | "reference" | "translated")[] = [
      "disabled",
      "reference",
      ...(policy ? ["translated" as const] : []),
    ];
    if (repeat % 2) conditions.reverse();
    for (const mode of conditions) {
      const episode = await createRoutingEpisode(mode, policy);
      let calls = 0,
        inputTokens = 0,
        outputTokens = 0,
        missingUsageCalls = 0,
        invalidProposals = 0;
      const failures: string[] = [];
      const started = performance.now();
      for (let round = 0; round < 3 && episode.view().remaining.length; round++) {
        const prompt = JSON.stringify({ task: scenario.task, state: episode.view() });
        let usageEvents = 0;
        const generate = connectionGenerator(connection, ROUTING_INSTRUCTIONS, 120_000, (u) => {
          usageEvents++;
          inputTokens += u.inputTokens;
          outputTokens += u.outputTokens;
        });
        calls++;
        let raw = "";
        let responseCompleted = false;
        let runtimeFailed = false;
        try {
          raw = await generate(prompt, (text) => {
            raw = text;
          });
          responseCompleted = true;
          const routes = parseRoutes(raw);
          if (!routes.length) break;
          for (const route of routes) {
            try {
              await episode.attempt(route);
            } catch (error) {
              if (error instanceof InvalidRouteError) invalidProposals++;
              else {
                failures.push("runtime_failed");
                runtimeFailed = true;
                break;
              }
            }
          }
        } catch {
          failures.push(responseCompleted ? "invalid_model_response" : "model_call_failed");
          if (responseCompleted) invalidProposals++;
        } finally {
          if (!usageEvents) missingUsageCalls++;
          save(`${repeat}-${scenario.id}-${mode}-${round}.json`, { prompt, response: raw });
        }
        if (runtimeFailed) break;
      }
      episodes.push({
        repeat,
        scenario: scenario.id,
        condition: mode,
        ...episode.result(),
        calls,
        invalidProposals,
        failures,
        tokenUsage: {
          status: missingUsageCalls ? "incomplete" : "provider_reported",
          inputTokens: missingUsageCalls ? null : inputTokens,
          outputTokens: missingUsageCalls ? null : outputTokens,
          observedInputTokens: inputTokens,
          observedOutputTokens: outputTokens,
          missingUsageCalls,
        },
        elapsedMs: Math.round(performance.now() - started),
      });
      save("results.json", {
        format: "nova-routing-agent-pilot-v1",
        model: connection.modelId,
        modelSettings: {
          maxTokens: connection.maxTokens,
          thinkingLevel: connection.thinkingLevel,
          reasoning: connection.reasoning,
        },
        repetitions: trials,
        instructions: ROUTING_INSTRUCTIONS,
        scenarios: ROUTING_CASES,
        instructionsHash: createHash("sha256").update(ROUTING_INSTRUCTIONS).digest("hex"),
        scope:
          "Model chooses routes; department payloads and auditor receipts are scripted through the shared backend port. Same policy prompt in every condition; only the receive gate changes. No reproducible model seed. This small pilot does not estimate general attack resistance or task quality.",
        tokenScope:
          "Provider-reported prompt tokens including cache read/write plus output tokens for routing calls and retries. Translation cost excluded; Datalog calls use no model tokens. Missing usage is unknown, never zero. Wall time is descriptive, not a benchmark.",
        artifactId: policy?.id,
        episodes,
      });
      console.log(
        JSON.stringify({
          repeat,
          scenario: scenario.id,
          condition: mode,
          complete: episode.result().completed,
          calls,
          usageComplete: !missingUsageCalls,
        }),
      );
    }
  }
