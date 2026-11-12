# Application policy translation

For the course workflow, use [the English student instructions](STUDENT.md).
`translate.py` accepts an original directory and a separate empty output directory;
`review.py --back-translation ... --policy ...` opens the saved execution reading
and writes student judgments directly to `review.json`. Git branches remain
user-owned.

The student entry reads `POLICY_API_KEY`, `POLICY_MODEL_ID` and
`POLICY_REASONING_EFFORT` from the environment. The model and reasoning effort
default to `gpt-6.1-sol` and `medium`. `POLICY_BASE_URL` selects a compatible API
endpoint; an explicit `--connection` file remains available for debugging.

The independent Python implementation lives in [`python/`](python/README.md).
It supplies requirements → shared rules → back-translation without Grokbot, Nova,
Node or a UI dependency. The [student workbench](../evaluation/README.md) composes
it with the separate policy and query layers. The TypeScript commands below remain
for the existing host and research experiments.

Generic authoring separates original NL, a traceable NL requirement plan, developer assessment and Datalog translation. Unsupported clauses, builtin mechanisms and backend obligations remain visible. Model generation is optional; reviewed Datalog can be compiled offline with either the Python or TS runtime.

## Interactive policy review

Run `pnpm --dir grokbot policy:review` from the repository root, then open
`http://127.0.0.1:5180/policy-review.html`. The Nova header also links to this page.
It starts with LabCluster's existing rules and explicitly hand-authored reference
readings; no model, native Datalog engine or application execution is needed.
Select original text to inspect linked behaviors, review unmapped requirements,
record differences and answer concrete intent questions. Conditions and application
input meanings expand on demand. Feedback and the latest model draft stay in the
browser; JSON export includes the exact source, rules, mappings and review identity.

For new translations, use the existing server-side `MODEL_CONNECTION_FILE`
connection described below and restart the server. Edit the numbered policy and
select Translate. Three model stages distill traceable requirements,
generate candidate rules, then explain the actual program. Back-translation receives
the candidate rules, relevant input meanings, configuration and fixed runtime
semantics, **not** the original policy or distilled statements. Shared rule references
produce many-to-many links. Each stage permits one correction after structural
validation fails; `generationAttempts` records both the failure and correction.
Text omitted during distillation is retained verbatim as unmapped review items;
`omittedRequirementIds` distinguishes these omissions from assessed unsupported
requirements. This does not relax the executable CLI's complete-source check.
Unsupported clauses remain review items. Provider
failure never falls back to the reference. Credentials never enter the browser.

This is a review draft using the fixed LabCluster vocabulary and configuration;
it cannot generate new adapters, change quotas in application configuration, or
establish runtime observation correctness. Structural checks reject invalid rules
and missing mappings, but do not prove that the descriptions or policies preserve
meaning. Original acceptance cases are not run against an edited policy. Integration
requirements are explicitly distinguished from rule behavior and are not verified
by this interface. Intent questions are prompts for human feedback, not executed
test cases. Ratings are not developer approval; no candidate is installed or offered
as an executable bundle. The existing reviewed CLI workflow remains separate.

Reference readings in `apps/labcluster-port/review-readings.json` are pinned to the
rule file, extracted shared rules and runtime contract. Changes require regenerating
the existing application artifacts and reviewing the readings before updating their
hashes. A stale reference is rejected rather than silently relabeled as current.

Offline UI checks: `pnpm --dir grokbot --filter @rakazo/web exec playwright test --config playwright.policy-review.config.ts`.
The CI Policy review UI job captures desktop, expanded-evidence, unmapped and mobile
screenshots without launching Electron or making model calls.

## Original NL → reviewed NL plan → Datalog

From the repository root:

```bash
pnpm --dir grokbot policy:translate apps/labcluster-port \
  --binding apps/labcluster-port/generated/runtime.json \
  --connection /path/to/private-models-connect.json
```

Without `--plan`, the generic command performs one distillation call and saves a candidate `policy-plan.json`. It returns `policy_review_required`, emits no executable bundle and does not request rules. The plan includes source spans, distilled statements, assumptions, observations, implementation classification and relation to the original wording. Every non-whitespace source character must be accounted for. This detects omitted spans, not semantic misinterpretation. Application documents are untrusted; the model cannot approve its own output.

Review the candidate against the real backend and the admitted Datalog fragment. A separate developer-supplied `policy-review.json` pins the exact plan hash, approves each requirement, supplies concrete verification obligations for builtin/backend coverage, and acknowledges every unsupported, ambiguous, partial, strengthened or weakened requirement. The plan also pins the original application documents, numbered source policies and complete trusted binding. Any such change invalidates the assessment. Review artifacts record an assessment; they do not prove equivalence or enforce access control against someone who can replace trusted application code.

Then translate only the approved Datalog targets:

```bash
pnpm --dir grokbot policy:translate apps/labcluster-port \
  --binding apps/labcluster-port/generated/runtime.json \
  --connection /path/to/private-models-connect.json \
  --plan apps/labcluster-port/generated/policy-plan.json \
  --review apps/labcluster-port/generated/policy-review.json
```

The checked-in LabCluster plan/review are developer-authored reference artifacts. A new model-distilled candidate needs its own assessment. `src/policy-plan.ts` exports `policyPlanHash` and the plan/review types; `apps/labcluster-port/tools/build_artifacts.py` demonstrates deterministic reference artifact authoring. `approvedRequirements` is the full list of IDs, `obligations` maps non-rule IDs to concrete verification descriptions, and `acknowledgedGaps` lists changed or unsupported IDs.

An assessment with no Datalog targets returns `reviewed_without_datalog`, saves coverage, calls no model and emits no executable authorization bundle.

The second model response contains shared `rules: [{id, datalog}]` and `coverage: [{id, ruleIds, notes}]`. Several requirements can reference one rule without duplicating it. Only Datalog targets require rule references; builtin/backend/unsupported requirements do not need fabricated clauses. Unknown rule references, missing targets and unreferenced rules fail validation. The assembled program must satisfy schema, head ownership, safety, stratification, resource limits and independent acceptance cases.

A successful run writes `policy-bundle.json`, the pinned plan/review and `coverage.json` under the ignored `translation/output/<binding-id>/<run-id>/`. Acknowledged gaps produce `validated_partial_policy_bundle`; complete assessed coverage produces `validated_policy_bundle`. Both retain `semanticCorrectness: unproven`. Source snapshots, prompts, raw response and failed validation remain available. The command never installs a running policy or modifies the app. No repair loop or reference-rule substitution occurs.

Application documents remain `app.md`, numbered `policy.md`, `tools.md` and `agents/*.md`; episodes are optional. The adapter developer supplies `runtime.json` or `--binding`: actual observation vocabulary, meanings, gate contract and independent acceptance cases. Tests stay out of model prompts. Datalog cannot invent authenticated identity, source evidence, transactions, semantic classifiers or future scheduler progress.

The generic compiler uses the bounded TS engine; the standalone Python/Soufflé loader independently reparses and validates the same version-2 bundle. [The Python adapter guide](../runtime/python/README.md) explains execution. [LabCluster adaptation record](../apps/labcluster-port/ADAPTATION.md) tests an actual external student backend with `--bundle`; its default reference run is explicitly authored, not a model experiment. [Document Vault](../apps/document-vault/README.md) remains the earlier independent TS example. Existing saved one-shot translations are historical evidence, not newly distilled runs.

## Existing Nova experiment

Nova supports two experiments. Add `--nova-extension` to provide the immutable foundation and fixed protocol and ask for app-specific extensions only. That path writes `nova-policy.json`, which Nova can review and load into a fresh session; see the [five-part walkthrough](../apps/nova/README.md). Its generated heads are limited to Deny, Covered and Finished; inputs, config, propagation rules and protocol cannot be rewritten. Unknown/unsafe/unstratified rules fail validation. One model call is made, with no repair or golden-rule substitution. Exact inputs and raw output are saved before validation, and failed behavior comparisons remain visible.

The command without `--nova-extension` preserves the legacy whole-policy experiment described below. Its artifacts are not installable Nova extension bundles.

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

## Natural-language query interpretation

`src/question.ts` is a provider-neutral one-shot interpreter. It accepts a question, a catalog of supported templates and named entities, plus an injected generation function. Its output is a template ID and parameters, a clarification, or an unsupported response—not executable query text. `src/model.ts` reuses the same models/connect adapter as policy translation.

Nova owns its template definitions, concrete questions and deterministic compiler in `apps/nova/src/questions.ts`. The web server composes these with the interpreter at `/nova-question`; it checks the selected state version both before and after interpretation. Only the existing analysis endpoint executes a query after the user reviews it. Examples use explicit deterministic bindings and are labeled separately from model interpretations. See [Nova setup](../apps/nova/README.md#natural-language-questions).

Question parameters may be entity strings or bounded arrays of message/route IDs. The Nova compiler validates candidate receipts, goal groups, starting states and routes, then creates analysis arguments deterministically. Raw Datalog or arbitrary event/action definitions from the model are not accepted. HTTP question requests use `mode: "model"` (the default) for genuine interpretation, or `mode: "example"` for an exact known offline example. Suggested questions only fill the input; they do not bypass the model when interpreted.
