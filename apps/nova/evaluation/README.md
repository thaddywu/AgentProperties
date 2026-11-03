# Nova research pilot

This is an exploratory evaluation of the current executable system. It separates policy expressiveness, translation fidelity and actual enforcement/task completion. It also exercises a new approval-service adapter through the generic runtime. It does not change production runtime behavior.

Run workspace commands from the repository root using its declared Node/pnpm versions. Native Soufflé 2.5 and Linux `prlimit` must be on `PATH`; installation is pinned in `grokbot/infra/compose/Dockerfile.nova`.

```bash
pnpm --dir grokbot exec tsx ../apps/nova/src/evaluation/run.ts \
  --output ../translation/output/nova-pilot-replay
pnpm --dir grokbot test apps/nova/tests/evaluation.test.ts
pnpm --dir grokbot --filter @rakazo/nova --filter @rakazo/policy-translation check
```

Use a new output directory for every execution. The runner refuses to overwrite an existing directory. Output contains a source-hash manifest and separate JSON reports for porting, RQ1, RQ2, RQ3, boundary probes and configuration-change counterexamples. Replaying the checked-in model artifacts is offline. No credentials or model are needed.

## Recorded model trials

`model-trials/trial-{1,2,3}.json` contain three unchanged current-protocol translation artifacts from separate real model invocations. These are generated outputs, including their errors. They are not handwritten replacements. JSON whitespace may be formatted; document strings, rules, notes, artifact identities and source-policy coverage remain unchanged. Each artifact is validated on loading.

The model was `gpt-6.1-sol`, using the shared OpenAI-compatible adapter, low reasoning and a 4096-token output limit. Each trial supplied the same current application documents, fixed foundation, vocabulary, configuration and protocol. Reference application rules, acceptance cases and the exploratory evaluation corpus were excluded from the prompt. There was no semantic repair, model-rule substitution or protocol generation. Existing adapter transport-retry behavior was inherited. No reproducible sampling seed was available. Three trials of one application/model do not estimate general translation accuracy.

The post-generation probes were developed after inspecting model output. They are explicitly **not held-out tests**. The fixed configuration and grouping-change scenarios are reported separately. Raw prompts, responses and metadata remain in ignored translation output; only reviewed fictional application artifacts are checked in.

To collect new model trials, use an explicitly selected private connection in the existing shared connection format:

```bash
pnpm --dir grokbot exec tsx ../translation/src/evaluation-run.ts \
  --connection /path/to/private-connection.json \
  --output ../translation/output/nova-model-trials \
  --trials 3
```

The shared adapter's public-endpoint configuration applies. The command makes real model requests and is excluded from ordinary tests. It writes `trial-N/nova-policy.json` plus raw evidence. To evaluate fresh artifacts, copy the reviewed artifact JSON files into a new directory named `trial-N.json`, then pass `--artifacts <directory>` to the offline runner. Model failures are reported by the translation driver, and unsuccessful trials must remain in a study's denominator. The replay runner only evaluates supplied validated artifacts; it does not estimate that denominator itself.

## Evaluation definitions

- **RQ1:** Maps the five current policies to required rules/mechanisms; tries eight compiler boundaries; executes two- and four-label threshold witnesses; includes eight manually annotated adaptations of public requirements. No population coverage claim is made. New input hooks, forbidden authority writes, compiler restrictions and missing runtime mechanisms are distinct limitations.
- **RQ2:** Checks the reference and each generated program on 1,472 enumerated local snapshots. Four group configurations, all subsets of three prior/incoming tags, three recipient identities and two capability states are considered. Sixty-four combinations with pre-existing forbidden exposure are excluded. Prior knowledge may survive capability revocation. Expected decisions, knowledge and coverage come from an independent set-based oracle, not reference Datalog. Fifty deterministic snapshots per program are cross-checked against native Soufflé. Actual configuration-change deliveries separately test completion.
- **RQ3:** Executes 288 workflows per condition: six department orders, eight recipient preferences, two capability configurations and three strategies. Sequential, interleaved and retry-the-other-auditor strategies each have 96 workflows. Conditions are an experimental no-gate control, reference enforcement and each eligible generated artifact. The no-gate control retains information-flow instrumentation but bypasses receive authorization inside this experiment only. Enforcement conditions use the real Nova `send`/`settle` API. Model artifacts failing the existing installation checks are not silently replaced or evaluated as deployable.
- **Safety:** Count a violation when an actually delivered message fails the independent capability/exposure monitor for that execution prefix. Check denied payload access, successful-receipt writes and outgoing lineage separately.
- **Completion:** Independently require all three original parts to have actually reached designated auditors. Compare this result to observer `Finished`. Safe completion additionally requires no prior violation. Scripts prescribe actions; there are no autonomous model agents in these workflows.
- **Porting:** Handwritten rules isolate adapter feasibility from translation quality. A new authorship/approval/publication vocabulary, renamed gate roles, self-review prohibition and dual approval use only the existing generic SDK. Same-session serialization, two independent sessions sharing a fake external effect counter and failure after an external effect demonstrate distinct boundaries.

The source manifest makes the evaluated code and input versions reviewable. These finite experiments do not establish universal equivalence, confidentiality of unobserved sources, distributed transaction safety, resistance to malicious host code, formal NIST compliance or statistically significant effectiveness in real agent deployments. Recorded elapsed times are cache/order dependent and are not performance benchmarks.

`locality.json` records two handwritten adversarial compiler/placement controls, separate from all model trials. They preserve the original reference program and add a foreign-principal dependency. Both pass the existing eight installation cases; an additional actual delivery then disagrees with full-copy evaluation of that same augmented program. The intended remote condition has no evidence route in the current protocol. This demonstrates an unsupported-policy validation gap, rather than a violation of the original Nova policies or a model-translation result. A sound port must reject such dependencies or provide authorized evidence and completeness guarantees.

[Findings and next experiments](../../../docs/nova-evaluation-pilot.md)
