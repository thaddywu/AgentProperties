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
