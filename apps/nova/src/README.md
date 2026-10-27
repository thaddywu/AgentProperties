# Nova implementation

Scripted application with six principals. Requires the root workspace dependencies, a supported Node version, Soufflé 2.5 and Linux `prlimit`. No API key, LLM or database is required for application execution.

Run from the repository root: `pnpm --filter @rakazo/nova start`. It executes the real initialization, sends and receives from the denial scenario and prints the blocked HR delivery. Start the UI with `./apps/nova/run.sh`.

`config.ts` and `shared.ts` define Nova's configuration and principals. `policy.ts` contains the unchanged hand-written reference rules. `runtime.ts`, `protocol.ts` and `local-store.ts` implement Nova's fact ownership, transport, send and receive gate. `analysis.ts` supplies Nova-specific what-if, prevention and action-search operations; `questions.ts` supplies that application's query examples. `service.ts` and its worker/process files expose the same backend to the Grokbot UI. Generic evaluation, syntax handling, provenance and lifecycle logic come from `@rakazo/policy-runtime` in the root `runtime/` directory.
