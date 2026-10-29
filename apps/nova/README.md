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

The background container keeps running after the terminal closes. Restart preserves the checkpoint in the `nova-reasoning-state` volume; New/Earlier/Denial explicitly reset the example state. `NOVA_PORT`, `NOVA_CONTAINER`, `NOVA_STATE_VOLUME` and `NOVA_IMAGE` select an isolated instance. The root launcher also supports `test`, `check` and `build`.

Without Docker, install Soufflé 2.5 and Linux `prlimit`, then run `pnpm --dir grokbot --filter @rakazo/web exec vite --config vite.nova.config.ts`. Set `NOVA_STATE_FILE` to persist local state. No LLM, database or episode file is needed for Nova execution.

## Execution and analysis

Each principal evaluates its own input store. Sending transports a snapshot of tracked labels; only a successful receive records knowledge and retains the labels. Denial withholds the payload and discards temporary gate facts. Trusted source assignment is separate from ordinary computations, and there is no automatic declassification.

The inspector's global view is assembled after independent local evaluation, not used as a shared policy store. Terminal queries do not install rules. Why, What-if, minimum prevention and completion search use the application's existing rules and protocol; the available search actions remain Nova-specific. Native evaluation and the worker retain their resource limits and failed-request rollback.

## Five-part policy walkthrough

Open **Rules** in the Nova UI:

1. **Runtime**: builtin EDB/IDB, six fixed IFC/capability rules, local placement and message transport. App-provided config values expand separately.
2. **Nova input**: app.md, policy.md, tools.md and agent descriptions. Episodes are not required or included in extension translation.
3. **Translated**: import `nova-policy.json`; inspect the exact source snapshot, per-policy builtin/extension coverage, generated rules and fixed inherited protocol. Validation runs before an explicit **Start translated session**. A failed artifact remains reviewable but cannot replace the active session.
4. **Golden**: handwritten Nova rules and complete fixed protocol. **Start golden session** returns to a fresh reference session.
5. **Prevention**: independent golden/generated sessions use actual send/settle calls. Inspect expected/actual decisions, Deny derivation, Received, payload visibility and closure differences. **Check closure union** compares the selected snapshot's merged local closures with full-copy evaluation of the same active rules, including Deny at each pending recipient.

The header identifies the active mode. New/Earlier/Denial reset data while retaining the active policy; switching policy explicitly starts a new initial session. Existing checkpoints without an artifact remain golden. Translated checkpoints carry the artifact identity and are validated on restore; incompatible artifacts fail instead of silently falling back. Query, Why, What-if, prevention search and replay follow that same policy.

Generate one real extension translation, independently of the UI:

```bash
pnpm --dir translation translate ../apps/nova --nova-extension --connection /path/to/private-connection.json
pnpm --dir apps/nova start --compare --policy ../../translation/output/nova/<run-id>/nova-policy.json
pnpm --dir apps/nova start --policy ../../translation/output/nova/<run-id>/nova-policy.json
```

The first command invokes the configured model once and stores the input, prompt, raw response, rules, artifact and results. It supplies fixed foundation rules and the protocol; golden app rules and test cases are excluded from the prompt. Syntax-valid artifacts are retained even when behavior mismatches, so they can be reviewed. The second command executes isolated comparisons and exits nonzero on a mismatch. The third starts the standalone denial demo only after the same checks pass. The legacy command without `--nova-extension` still generates an entire policy for its original comparison experiment.

Eight predefined scenarios cover ordinary messages, capability absent/present, a third distinct tag, all-three incoming and the Board exception, non-goal groups, repeated/unrelated tags, and historical audit receipts. Checks compare all final closure facts and recipient-visible messages, and compare full-copy Deny at each tested delivery. They are finite conformance checks, not proof of natural-language correctness or equivalence across all executions. Full-copy evaluation is diagnostic only and never supplies a gate's decision. EDB copy counts exclude message bodies, history snapshots and rule-storage costs; they do not establish a global minimum.

Protocol generation/minimization is still a research proposal. Nova's adapter implements the fixed hooks; the extracted declarations are not an automatic interceptor for arbitrary frameworks. The message lifecycle affects inference through Incoming/Received and the receive gate. The separate resource lifecycle relations are not part of Nova's denial rules. See the [protocol-plan proposal](../../docs/distributed-protocol-rq.md).
