# Nova policy translation prototype

One real LLM invocation translates the entire Markdown policy set directly into Datalog. This package is separate from the Nova runtime; it does not install rules or change enforcement. There is no IR, policy template, repair loop or reference-rule substitution.

Use the workspace's supported Node version and pnpm. From the repository root:

```bash
pnpm install --frozen-lockfile
pnpm policy:translate apps/nova --connection /path/to/private-models-connect.json
```

The private connection file uses the existing `ModelConnectInputSchema` / models/connect format: `provider`, `modelId`, `apiKey`, and, for `openai-compatible`, `baseUrl`; optional `maxTokens`, `thinkingLevel`, `reasoning`, `contextWindow`. Keep it outside the public repository. API credentials are passed to the existing Pi adapter, never written to experiment metadata. This CLI does not read credentials from another application's authentication files or from the encrypted product database.

Alternatively, use `--provider <provider> --model <model> --api-key-env <existing-variable>` and optionally `--base-url <url>`. Existing `PI_DEFAULT_PROVIDER`, `PI_DEFAULT_MODEL` and the runtime's OpenRouter fallback are reused. No translation-specific provider variables are introduced. Keyless local compatible servers are supported through the standard connection. No mock fallback exists in the CLI.

Artifacts go to ignored `translation-output/nova/<run-id>/`: exact input Markdown snapshots, prompt, non-secret model settings/source revision, raw response (also partial output on failure), generated Datalog, results and a short report. Missing model configuration produces a failed-run report, not fabricated Datalog. Treat raw responses/experiment files as private until reviewed.

Output is JSON with a `policies` array of `{ id, datalog, notes }`. Every source policy must be represented; an empty Datalog string with an explanation is allowed and flagged for semantic review. The model uses the existing terminal dialect: periods, `:-`, `not`, `!=`, quoted constants; no Souffle directives or queries. The existing parser and serializer adapt this syntax without changing the policies. Unknown predicates, wrong arities and writes to runtime-owned input relations are reported. Both combined-program TypeScript checks and native Souffle evaluation are attempted; native validation needs `souffle` and Linux `prlimit` on PATH. The existing pinned installation is documented in `infra/compose/Dockerfile.nova`.

Reference rules are imported only after generation, for a small set of local-store probes comparing observable results. Compilation or matching those probes does not prove equivalence. Payload isolation, atomic delivery and end-to-end runtime behavior are not tested by this prototype. Model runtime transport retry defaults are inherited; there is no semantic repair or second translation attempt.

```bash
pnpm exec vitest run translation/src grokbot/packages/adapters/src/policy-translation.test.ts
pnpm --filter @rakazo/policy-translation check
```

Ordinary tests are offline and use synthetic model output. They are not translation experiment results.
