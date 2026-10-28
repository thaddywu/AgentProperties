# Application policy translation

One real LLM invocation translates an application's Markdown policies directly into Datalog. Applications with a trusted runtime binding can export a validated bundle that their adapter loads into the generic runtime gate. There is no IR, policy template, repair loop or reference-rule substitution.

## Application → translation → runtime

```bash
pnpm --dir grokbot install --frozen-lockfile
pnpm --dir translation translate ../apps/document-vault --connection /path/to/private-models-connect.json
pnpm --dir apps/document-vault start --bundle ../../translation/output/document-vault/<run-id>/policy-bundle.json
```

The application description is `app.md`, numbered `policy.md`, `tools.md` and `agents/*.md`. Episodes are optional, and the framework accepts one or more policies. A developer supplies the separate adapter-owned `runtime.json` (or `--binding <path>`): observed predicates, argument order, decision outputs, runtime guarantees and independent acceptance cases. This file documents actual instrumentation; it is not a student-authored policy language or a model-generated authority source.

The generic path has no Nova schema, reference rules, comparison oracle or Nova imports. It sends only the binding's vocabulary/context and application Markdown to the model; acceptance cases stay out of the prompt. Validation uses the shared bounded TypeScript Datalog engine. Successful validation produces `policy-bundle.json` under `translation/output/<binding-id>/<run-id>/`. Unknown predicates, input writes, unsafe rules, negative recursion, failed cases or empty policy translations prevent bundle creation. The application explicitly loads the artifact and revalidates it against its trusted binding before use. The CLI itself does not launch the application or modify a running session.

The [Document Vault walkthrough](../apps/document-vault/README.md) exercises actual allowed/denied callbacks and query/Why/What-if using that artifact. [Runtime API](../runtime/README.md) describes the porting contract and transaction limits. A third-party app can call the same SDK from its own trusted adapter; source-code instrumentation is still the developer's responsibility.

## Existing Nova experiment

Use the workspace's supported Node version and pnpm. Install the workspace once, then run this package directly from the repository root:

```bash
pnpm --dir grokbot install --frozen-lockfile
pnpm --dir translation translate ../apps/nova --connection /path/to/private-models-connect.json
```

Or, from `translation/`, run `pnpm translate ../apps/nova --connection /path/to/private-models-connect.json`. Application/connection paths and an explicit `--output` are relative to that command's working directory. The legacy Nova output stays in this package's `output/nova/`; generic applications use `output/<binding-id>/`, regardless of where the CLI is launched.

No Grokbot UI, API, worker or database service needs to be running. The CLI still reuses Grokbot's model adapter/contracts through workspace dependencies; it is not yet a separately installable distribution without the rest of this checkout. The existing root-workspace alias `pnpm --dir grokbot policy:translate apps/nova ...` also works.

The private connection file uses the existing `ModelConnectInputSchema` / models/connect format: `provider`, `modelId`, `apiKey`, and, for `openai-compatible`, `baseUrl`; optional `maxTokens`, `thinkingLevel`, `reasoning`, `contextWindow`. Keep it outside the public repository. API credentials are passed to the existing Pi adapter, never written to experiment metadata. This CLI does not read credentials from another application's authentication files or from the encrypted product database.

Alternatively, use `--provider <provider> --model <model> --api-key-env <existing-variable>` and optionally `--base-url <url>`. Existing `PI_DEFAULT_PROVIDER`, `PI_DEFAULT_MODEL` and the runtime's OpenRouter fallback are reused. No translation-specific provider variables are introduced. Keyless local compatible servers are supported through the standard connection. No mock fallback exists in the CLI.

Artifacts go to ignored `translation/output/nova/<run-id>/`: exact input Markdown snapshots, prompt, non-secret model settings/source revision, raw response (also partial output on failure), generated Datalog, results and a short report. Missing model configuration produces a failed-run report, not fabricated Datalog. Treat raw responses/experiment files as private until reviewed.

Output is JSON with a `policies` array of `{ id, datalog, notes }`. Every source policy must be represented; an empty Datalog string with an explanation is allowed and flagged for semantic review. The model uses the existing terminal dialect: periods, `:-`, `not`, `!=`, quoted constants; no Souffle directives or queries. The existing parser and serializer adapt this syntax without changing the policies. Unknown predicates, wrong arities and writes to runtime-owned input relations are reported. Both combined-program TypeScript checks and native Souffle evaluation are attempted; native validation needs `souffle` and Linux `prlimit` on PATH. The existing pinned installation is documented in `grokbot/infra/compose/Dockerfile.nova`.

In the legacy Nova path, reference rules are imported only after generation, for a small set of local-store probes comparing observable results. Compilation or matching those probes does not prove equivalence. Those legacy Nova probes do not test payload isolation, atomic delivery or runtime installation. The separate generic application tests exercise callback prevention and observation commits, not distributed transactions. Model runtime transport retry defaults are inherited; there is no semantic repair or second translation attempt.

```bash
pnpm --dir grokbot test translation/src grokbot/packages/adapters/src/policy-translation.test.ts
pnpm --dir grokbot --filter @rakazo/policy-translation check
```

Ordinary tests are offline and use synthetic model output. They are not translation experiment results.

The recorded GPT-6.1 Sol one-shot matched all fourteen baseline probes, while the historical-audit-receipt counterexample still failed. See the [model comparison](../docs/translation-model-comparison.md) for the limitations and the GPT-5.4 comparison; no new model invocation is performed by installing or testing this package.

To repeat that model configuration, keep the following shared-connection JSON outside this repository and replace the key placeholder. The installed Pi native catalog did not include this model, so that run used the compatible adapter. The model ID and low reasoning setting are listed in the [official OpenAI documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

```json
{
  "provider": "openai-compatible",
  "modelId": "gpt-6.1-sol",
  "baseUrl": "https://api.openai.com/v1",
  "apiKey": "YOUR_API_KEY",
  "reasoning": true,
  "thinkingLevel": "low",
  "maxTokens": 8192
}
```

For that public endpoint, explicitly enable the existing compatible-adapter gate for this invocation:

```bash
RAKAZO_OPENAI_COMPAT_ALLOW_PUBLIC=1 pnpm --dir translation translate ../apps/nova \
  --connection /path/to/private-models-connect.json
```
