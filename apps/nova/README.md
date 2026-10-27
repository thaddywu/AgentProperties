# Nova

`app.md`, `policy.md`, `tools.md` and `agents/` define the application specification. LLM agents supply their real system prompts; Nova supplies scripted decision logic. `episodes/` contains optional examples and may be omitted. `src/` contains the actual scripted application, reference policies, message protocol, local stores and Nova-specific analyses. `tests/` exercises those real transitions. The Grokbot UI is a separate client.

From the repository root, install workspace dependencies and provide Soufflé 2.5 plus Linux `prlimit` on PATH:

```bash
pnpm --filter @rakazo/nova start
pnpm --filter @rakazo/nova test
pnpm policy:translate apps/nova --connection /path/to/private-connection.json
./nova-demo.sh
```

The first command runs the denial scenario without a UI, LLM or database. The last command opens the existing Grokbot-based UI with the same application backend. See `src/README.md` for implementation/run details and `../../docs/repository-structure.md` for boundaries.

Student applications can eventually provide a binding to the shared runtime. Nova's current `send`/`settle` and service intents are an example, not a fixed general-purpose contract. Episodes are examples, not the execution interface. No student archives are generated here.

## UI setup and lifecycle

From the repository root:

```bash
./nova-demo.sh setup  # First-time image build/download
./nova-demo.sh        # Start or restart at http://127.0.0.1:5180/
./nova-demo.sh status
./nova-demo.sh logs
./nova-demo.sh stop
```

The background container keeps running after the terminal closes. Restart preserves the checkpoint in the `nova-reasoning-state` volume; New/Earlier/Denial explicitly reset the example state. `NOVA_PORT`, `NOVA_CONTAINER`, `NOVA_STATE_VOLUME` and `NOVA_IMAGE` select an isolated instance. The root launcher also supports `test`, `check` and `build`.

Without Docker, install Soufflé 2.5 and Linux `prlimit`, then run `pnpm --filter @rakazo/web exec vite --config vite.nova.config.ts`. Set `NOVA_STATE_FILE` to persist local state. No LLM, database or episode file is needed for Nova execution.

## Execution and analysis

Each principal evaluates its own input store. Sending transports a snapshot of tracked labels; only a successful receive records knowledge and retains the labels. Denial withholds the payload and discards temporary gate facts. Trusted source assignment is separate from ordinary computations, and there is no automatic declassification.

The inspector's global view is assembled after independent local evaluation, not used as a shared policy store. Terminal queries do not install rules. Why, What-if, minimum prevention and completion search use the application's existing rules and protocol; the available search actions remain Nova-specific. Native evaluation and the worker retain their resource limits and failed-request rollback.
