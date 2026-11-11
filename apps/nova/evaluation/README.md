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

## Three-RQ lab: observable equality and measured model usage

The updated [evaluation plan](../../../docs/research/main.tex) separates manual scope review, translation correctness, and actual safety/completion/cost. The new lab complements the earlier pilot above; it does not overwrite historical outputs.

```bash
# Offline: manual RQ1 inventory, exact positive-UCQ fragment, recursive tests and execution control.
pnpm --dir grokbot exec tsx ../apps/nova/src/evaluation/lab-run.ts \
  --output ../translation/output/nova-rq-lab

# Real routing model: explicit private shared connection, optional existing translated artifact.
pnpm --dir grokbot exec tsx ../translation/src/nova-agent-evaluation.ts \
  --connection /path/to/private-connection.json \
  --artifact ../apps/nova/evaluation/model-trials/trial-1.json \
  --trials 2 --output ../translation/output/nova-rq-model

pnpm --dir grokbot test apps/nova/tests/research-lab.test.ts grokbot/packages/adapters/src/policy-translation.test.ts
```

Use a new output directory. A public model endpoint uses the host's existing explicit public-endpoint connection setting; credentials and connection files remain private. Ordinary tests and the offline lab make no model calls. The model driver records partial responses privately and retains failure/missing-usage records. Its three-round limit and 1–5 repetition limit bound the experiment. Configure the model/output limit through the existing connection format.

The lab uses the old predicate names when replaying unchanged artifacts; `HasReceivedTag` corresponds to the public `Knows` primitive. The routing experiment uses the canonical shared backend port.

- **RQ1:** The five Nova policies are manually mapped to rules, trusted observations and required mechanisms; eight boundary probes supplement the analysis. This is an inventory, not a population expressiveness score. A larger study needs a stated corpus, two independent annotators, unresolved/unsupported policies and executable witnesses.
- **RQ2, exact fragment:** `compareUcq` implements bidirectional containment via each branch's canonical database, with fresh values for variables and fixed constants. It accepts only parsed flat positive relational UCQs under set semantics, no recursion, negation, comparisons or integrity constraints. `Covered` is checked with `MessageTag` treated as a leaf input. This is a fragment result, not a proof for the recursive full program. The missing-TagGroup witness is also replayed through actual Nova deliveries under an accepted configuration change.
- **RQ2, full program:** Each of three saved model outputs is compared to the reference on the earlier 1,472-snapshot domain and 2,048 additional graph-shaped EDBs. The latter vary six edges, three seed labels, current capability and hiring-group membership. They include cycles and already-exposed recipients as semantic stress inputs; these are not all reachable workflow histories. Results are partitioned by prior exposure. `Deny`, received knowledge, `Covered` and `Finished` are reported separately. A graph-reachability oracle checks shared recursive propagation. A handwritten missing-propagation control verifies that the tests detect an error; it is not a model translation trial. The separate bounded-SAT command below now implements this search; the earlier lab command retains its original UCQ/testing outputs.
- **RQ3:** The model selects routes; departmental reports and auditor receipts remain scripted. Every condition gets the same policy prompt and initial state. Only the gate changes: disabled, reference, or translated. Attempts pass through the actual shared port/delivery callback. An independent set-based monitor checks released parts; completion requires all parts to reach designated auditors. A fixed bad-routing script is a separate positive control, not a model outcome.
- **Tokens:** The shared adapter exposes provider-reported usage events. Prompt tokens include cache reads/writes under its existing accounting. Output tokens are reported separately. Counts include every routing call and retry, including failed tasks; absent usage is null/unknown. There is no tokenizer estimate or claim about billing prices. Datalog calls use zero model tokens; one-time translation is excluded from these task totals and must be measured separately in a larger study.

Recorded results and source hashes are in [nova-rq-lab](../../../docs/evaluation/nova-rq-lab/). In the configured live pilot, two tasks × two repetitions × three conditions produced 12 completed, safe runs, each with one call. Because the disabled baseline also had zero violations, this sample does not demonstrate a safety improvement or prompt-injection resistance. It does show that token costs can be recorded through the real adapter. There are no configured-run model/parse failures; an earlier connection-setup block is recorded separately from policy performance.

For RQ2, all three outputs differ on 64 of 2,048 denial tests, confined to already-exposed recipients; the other 1,920 have no denial differences. All three also differ on coverage in 512 and completion in 128 tests when grouping is changed. The older 1,472 tests excluded prior exposure and therefore did not find those extra denials. Neither corpus was frozen before the outputs were inspected. Finding a disagreement is conclusive for that EDB; finding none is not universal equality.

## Bounded SAT and configurable testing

The SAT checker accepts the **full function-free stratified Datalog program**, including positive recursion, negation and `!=`; it does not require UCQ. It compares only declared output predicates. A finite EDB catalog lists required and optional tuples, with explicit clauses restricting allowed combinations. Every other EDB tuple is absent. This defines the scope of the result; it is not a bound on all possible deployments or traces.

```bash
# SAT + reproducible sampled EDB tests + actual port traces; no model or native solver required.
pnpm --dir grokbot exec tsx ../apps/nova/src/evaluation/sat-run.ts \
  --output ../translation/output/nova-sat \
  --seed 239 --cases 512 --traces 16 --steps 12 --cnf

# Also exhaust the finite catalog and replay SAT witnesses with native Soufflé.
pnpm --dir grokbot exec tsx ../apps/nova/src/evaluation/sat-run.ts \
  --output ../translation/output/nova-sat-exhaustive \
  --testing exhaustive --cases 16384 --traces 16 --steps 12 --seed 239 --cnf --native

pnpm --dir grokbot test apps/nova/tests/bounded-equivalence.test.ts
```

Use a new output directory. `--artifact <file>` selects a single validated artifact; otherwise all three saved trials run. `--timeout` bounds each solver subprocess in milliseconds (default 10,000, maximum 60,000). `--native` alone requires the existing Soufflé/prlimit installation. `--cnf` emits standard DIMACS plus a mapping from SAT variables to optional EDB facts. It does not enable raw fact assertion in a running app.

`runtime/src/bounded-equivalence.ts` is backend-neutral. The optional Nova research adapter uses [Logic Solver's MiniSat backend](https://github.com/meteor/logic-solver), pinned as a development dependency and isolated in a child with wall-time, V8 heap and output limits. The runtime core imports no solver package. `runtime/src/finite-domain.ts` provides exhaustive/seeded testing, observation projection, evaluator replay and counterexample shrinking. Other applications can supply the same schema/rule/input-space contract and a SAT backend.

The encoder first finds a finite over-approximation of possible ground rules. **It does not treat that over-approximation as true.** Derived tuples start false. For each rule stratum, the circuit performs as many synchronous inference rounds as there are possible derived tuples in that stratum; that suffices to reach its least fixed point. Negation reads completed lower strata or EDB variables. Both programs share the same EDB variables. The final constraint asks whether any chosen output differs. Tests specifically check that unsupported recursive facts cannot justify themselves.

Results distinguish:

| Status | Meaning |
| --- | --- |
| `different` | A concrete EDB gives different observed answers; the evaluator replays it and optional tuples are deletion-shrunk. |
| `equivalent_within_bound` | SAT is UNSAT, or exhaustive testing completed, for exactly this catalog and its constraints. |
| `tested_no_difference` | Sampled/budget-limited testing found no difference; no equality claim. |
| `empty_domain` | The constraints admit no EDB; not reported as a useful equality result. |
| `inconclusive` | Timeout, resource quota, invalid solver model, failed replay, or insufficient round budget. |
| `unsupported` | Invalid schema/writers, unsafe rules or unstratified negation. |

Every SAT model is checked against the generated CNF before replay. Shrinking preserves required facts and domain clauses; it seeks deletion-minimal optional facts, not a globally smallest EDB. Exhaustive testing reports both examined assignments and admitted cases. Sampled testing records its seed and includes boundary subsets before random inputs. Neither can silently extend the catalog's scope.

Trace testing uses two actual shared ports, the same intent sequence and fixed or missing-hiring-group configuration. A legal split is followed by a relay cycle and seeded sends/revocations. Runtime events are generated by the port; capability facts come from a versioned authoritative producer. Comparison stops at the first differing prefix and records delivery outcomes, actual releases, knowledge, coverage and completion. Raw EDB counterexamples may be unreachable; these trace counterexamples are actual port executions. The deliberately changed grouping is reported, not hidden as a normal fixed-config failure.

Recorded [SAT/testing evidence](../../../docs/evaluation/nova-sat/) uses the unchanged three artifacts. Each has the same result: a denial counterexample in the unconstrained 13-tuple catalog; denial equality after excluding prior exposure (all 8,192 assignments checked, 7,168 admitted); and a completion counterexample in the 14-tuple catalog when hiring-group membership can be absent. Every found SAT witness also passes native replay. Each artifact's 16 traces compare 120 steps and expose eight task-output differences in the missing-group configuration. This is exploratory evidence, not held-out accuracy or universal equivalence.
