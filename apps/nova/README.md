# Nova

`app.md`, `policy.md`, `tools.md` and `agents/` define the application specification. LLM agents supply their real system prompts; Nova supplies scripted decision logic. `episodes/` contains optional examples and may be omitted. `src/` contains the actual scripted application, reference policies, message protocol, local stores and Nova-specific analyses. `tests/` exercises those real transitions. The Grokbot UI is a separate client.

From the repository root, install workspace dependencies and provide Soufflé 2.5 plus Linux `prlimit` on PATH:

```bash
pnpm --dir grokbot --filter @rakazo/nova start
pnpm --dir grokbot --filter @rakazo/nova test
pnpm --dir translation translate ../apps/nova --connection /path/to/private-connection.json
./apps/nova/run.sh
```

The first command runs the denial scenario without a UI, LLM or database. The last command opens the existing Grokbot-based UI with the same application backend. See `src/README.md` for implementation/run details and `../../docs/repository-structure.md` for boundaries.

Student applications can eventually provide a binding to the shared runtime. Nova's current `send`/`settle` and service intents are an example, not a fixed general-purpose contract. Episodes are examples, not the execution interface. No student archives are generated here.

## UI setup and lifecycle

From the repository root:

```bash
./apps/nova/run.sh setup  # First-time image build/download
./apps/nova/run.sh        # Start or restart at http://127.0.0.1:5180/
./apps/nova/run.sh status
./apps/nova/run.sh logs
./apps/nova/run.sh stop
```

The background container keeps running after the terminal closes. Restart preserves the checkpoint in the `nova-reasoning-state` volume; New / Before second delivery / Before third delivery explicitly reset the example state. `NOVA_PORT`, `NOVA_CONTAINER`, `NOVA_STATE_VOLUME` and `NOVA_IMAGE` select an isolated instance. The root launcher also supports `test`, `check` and `build`.

Without Docker, install Soufflé 2.5 and Linux `prlimit`, then run `pnpm --dir grokbot --filter @rakazo/web exec vite --config vite.nova.config.ts`. Set `NOVA_STATE_FILE` to persist local state. No LLM, database or episode file is needed for Nova execution.

## Execution and analysis

Each principal evaluates its own input store. Sending transports a snapshot of tracked labels; only a successful receive records knowledge and retains the labels. Denial withholds the payload and discards temporary gate facts. Trusted source assignment is separate from ordinary computations, and there is no automatic declassification.

The inspector's global view is assembled after independent local evaluation, not used as a shared policy store. Terminal queries do not install rules. Why, What-if, minimum prevention and completion search use the application's existing rules and protocol; the available search actions remain Nova-specific. Native evaluation and the worker retain their resource limits and failed-request rollback.

## Five-part policy walkthrough

Open **Rules** in the Nova UI:

1. **Runtime**: builtin EDB/IDB, six fixed IFC/capability rules, local placement and message transport. App-provided config values expand separately.
2. **Nova input**: app.md, policy.md, tools.md and agent descriptions. Episodes are not required or included in extension translation.
3. **Translated**: import `nova-policy.json`; inspect the exact source snapshot, per-policy builtin/extension coverage, generated rules and fixed inherited protocol. Validation runs before an explicit **Start translated session**. A failed artifact remains reviewable but cannot replace the active session.
4. **Reference**: handwritten Nova rules and complete fixed protocol. **Start reference session** returns to a fresh reference session.
5. **Prevention**: independent golden/generated sessions use actual send/settle calls. Inspect expected/actual decisions, Deny derivation, Received, payload visibility and closure differences. **Check closure union** compares the selected snapshot's merged local closures with full-copy evaluation of the same active rules, including Deny at each pending recipient.

The header identifies the active mode. New / Before second delivery / Before third delivery reset data while retaining the active policy; switching policy explicitly starts a new initial session. Existing checkpoints without an artifact remain in reference mode. Translated checkpoints carry the artifact identity and are validated on restore; incompatible artifacts fail instead of silently falling back. Query, Why, What-if, prevention search and replay follow that same policy.

Generate one real extension translation, independently of the UI:

```bash
pnpm --dir translation translate ../apps/nova --nova-extension --connection /path/to/private-connection.json
pnpm --dir apps/nova start --compare --policy ../../translation/output/nova/<run-id>/nova-policy.json
pnpm --dir apps/nova start --policy ../../translation/output/nova/<run-id>/nova-policy.json
```

The first command invokes the configured model once and stores the input, prompt, raw response, rules, artifact and results. It supplies fixed foundation rules and the protocol; golden app rules and test cases are excluded from the prompt. Syntax-valid artifacts are retained even when behavior mismatches, so they can be reviewed. The second command executes isolated comparisons and exits nonzero on a mismatch. The third starts the standalone denial demo only after the same checks pass. The legacy command without `--nova-extension` still generates an entire policy for its original comparison experiment.

Eight predefined scenarios cover ordinary messages, capability absent/present, a third distinct tag, all-three incoming and the Board exception, non-goal groups, repeated/unrelated tags, and split audit completion. Checks compare all final closure facts and recipient-visible messages, and compare full-copy Deny at each tested delivery. They are finite conformance checks, not proof of natural-language correctness or equivalence across all executions. Full-copy evaluation is diagnostic only and never supplies a gate's decision. EDB copy counts exclude message bodies, history snapshots and rule-storage costs; they do not establish a global minimum.

Protocol generation/minimization is still a research proposal. Nova's adapter implements the fixed hooks; the extracted declarations are not an automatic interceptor for arbitrary frameworks. The message lifecycle affects inference through Incoming/Received and the receive gate. The separate resource lifecycle relations are not part of Nova's denial rules. See the [protocol-plan proposal](../../docs/distributed-protocol-rq.md).

## Replay and compare on screen

The home-page **View historical translation** button loads the reviewed real-model snapshot in `demo/translation.json`, shows the recorded historical validation and prevention cases, and opens a per-policy comparison. It makes no model call and leaves the active session and its messages unchanged. **Policy** selects P1–P5: the source paragraph appears above **Reference (historical)** and **Generated** columns. Builtin coverage is explicitly labeled instead of showing empty output as a missing translation. Runtime support for P4 remains visible because preventing payload release requires code as well as Datalog.

**Rules → Runtime** shows the foundation rules and protocol. **Rules → Reference → Nova protocol** shows only Nova's additions; **Complete protocol** expands the composed contract. The replay intentionally retains the old-protocol P5 output and its old reference comparison. It is a historical display, not a rerun against the new runtime. It cannot activate the saved candidate, and its seven matching scenarios are not a general correctness claim. The synthetic browser fixture used to test activation is separate from this real-model snapshot.

## Local enforcement and global completion

`Covered(Tag)` is derived in each auditor's store. There is no audit-summary transfer or audit-receipt predicate. Only the global observer evaluates `Finished(Group)` over the union of independently computed local closures. It never reruns local rules over the union, and no principal's store contains Finished. Query, Why, What-if and completion search use this observer result when a global goal is requested. Local rules cannot depend on Finished.

The demo keeps its designated auditors fixed. Reference checkpoints upgrade to protocol version 3 by dropping obsolete summary records while preserving messages, decisions and event snapshots. Old translated artifacts are rejected by their foundation/protocol identity; they are never silently repaired or replaced. The saved demo output remains historical, and new translations receive the new protocol.

## Vocabulary

Current names: `MessageTag` (formerly `Propagated`), `HasReceivedTag` (`Knows`), `Covered` (`Audited`), `ReceivedBeforeSend` (`Before`), and `MayDependOn` (`DependsOn`). `Received` is the single successful-delivery fact; the duplicate `Receiver` has been removed. Existing reference checkpoints migrate facts, envelopes and event snapshots. Historical model output keeps its original vocabulary and cannot be installed into the current runtime.

## Natural-language questions

Open **Questions** and type a specific question, for example “Why can't Auditor A receive the pending HR message?” on **Before third delivery**. **Interpret question** selects a supported template and resolves its parameters. The terminal shows the original question, a concrete interpretation, the generated query, scope and snapshot; run the analysis separately. Interpretation cannot send messages, change permissions or replay a plan.

The model receives template descriptions, principal names, known tag IDs, message IDs/from/to/status and the selected snapshot label. It receives no message bodies, private connection data, full store contents or reference rules. The server validates the selected template and entities, binds local/global scope, and constructs quoted Datalog constants. Unknown entities, recipient mismatches and stale revisions are rejected. Ambiguous or unsupported questions produce a message instead of an executable query. This is constrained interpretation, not unrestricted natural-language-to-Datalog generation.

**Open example** works offline and is labeled **Example**. **Interpret question** always calls the configured model, even for exact example wording, and is labeled **Model interpretation**; there is no silent mock fallback. For a model, reuse a private [models/connect JSON](../../translation/README.md) outside the repository:

```bash
./apps/nova/run.sh setup  # Rebuild once after upgrading the demo
MODEL_CONNECTION_FILE=/path/to/private-models-connect.json ./apps/nova/run.sh
```

The launcher mounts this file read-only in the container. For a public endpoint through the existing `openai-compatible` adapter, also set its existing gate `RAKAZO_OPENAI_COMPAT_ALLOW_PUBLIC=1`. Without Docker, set `MODEL_CONNECTION_FILE` when starting Vite. No key is sent to the browser or written to the saved runtime state. Restart with the same settings to retain the optional model connection.

Supported questions cover source messages, tag holders, message tags, permissions, missing permissions, refusal explanations, a hypothetical removed receipt, minimum prevention over selected receipt events, provenance, current completion and planning from a selected or earlier starting state. The model does not invent new templates or a new search domain. Queries still require review: valid parameter binding does not prove correct interpretation of every natural-language question.

Four fill-only suggestions above **Ask about Nova** cover Why, What-if, Min-prevention and Planning. For the first three, select **Before third delivery** or the Before/Gate inputs snapshot of the HR refusal event. Planning can select either the earlier starting state or the current selected snapshot; selected-state planning requires pending deliveries to be resolved first.

Interpretation includes the actual parameters: recipient/message for Why; an earlier receipt for What-if; recipient/message and an array of candidate receipt message IDs for Min-prevention; goal group, starting-state choice and an array of allowed route IDs for Planning. These compile into FACT, REMOVE/ADD, PREVENTABLE EVENTS or GOAL/PROGRESS ACTIONS. Opening another interpretation replaces all corresponding form arguments, including clearing an old ADD field. Bindings are inspectable under **Interpreted arguments**. What-if currently only supports removing one receipt, so ADD is explicitly empty rather than an invented model output. Candidate events are single successful receipts; allowed routes come from Nova's existing action domain.

## Backend-neutral port and FSM experiment

`src/ports.ts` composes Nova's reference rules or a validated saved translated extension with the canonical shared primitives. Both target `createBackendPort`; the application supplies principals, grants, audit rules and authorized observation/effect functions.

```bash
pnpm --dir grokbot exec tsx ../apps/nova/src/port-demo-run.ts --output ../translation/output/nova-port-run
# Optionally add --artifact ../apps/nova/evaluation/model-trials/trial-1.json
```

Use a new output directory. The trial enumerates bounded fact/rule placements over 190 generated snapshots, checks local gates and four query observations, executes the selected plan with real delivery callbacks, and drives an audit report through `draft → approved → published`. A rejected hiring report never reaches the delivery sink. Observer completion is explicitly materialized at the report authority, rather than read implicitly by local gates. `results.json` records scope, costs, hashes and execution outcomes.

This is an offline integration/placement experiment with synthetic data. It does not measure production latency or prove correctness for all asynchronous executions. See [the port contract](../../docs/application-porting-contract.md#8-implemented-interfaces-and-primitive-vocabulary) for trusted EDB producers, recovery and the optional Grokbot adapter's required host hooks.

The [three-RQ lab](evaluation/README.md#three-rq-lab-observable-equality-and-measured-model-usage) adds exact positive-UCQ fragment comparisons, recursive EDB tests and an optional real routing-model experiment with measured token usage.
