# Document Vault: translated policy in a running application

This independent application demonstrates Markdown → one model invocation → validated policy bundle → actual gated document reads → query, Why and What-if. It imports only `@rakazo/policy-runtime`; it has no Nova, Grokbot-service, database, UI or native Soufflé dependency. The workspace still installs through `grokbot/`.

`app.md`, `policy.md`, `tools.md` and `agents/service.md` are the application description. The agent is scripted. There are no episodes. `runtime.json` is an adapter-owned instrumentation contract: predicate names/argument order, trusted observations, decision outputs and independent allow/deny acceptance cases. It is supplied by the developer porting the app, not invented by the translation model or required as part of every student's Markdown submission. `--binding` can point to a contract kept outside the application directory.

From the repository root:

```bash
pnpm --dir grokbot install --frozen-lockfile
pnpm --dir translation translate ../apps/document-vault --connection /path/to/private-connection.json
pnpm --dir apps/document-vault start --bundle ../../translation/output/document-vault/<run-id>/policy-bundle.json
```

For the previously used public OpenAI-compatible connection, prefix the translation command with `RAKAZO_OPENAI_COMPAT_ALLOW_PUBLIC=1`; see [model connection configuration](../../translation/README.md). Only translation invokes a model. Replaying a saved bundle is offline and needs only Node/pnpm. The runner requires an explicit bundle and never falls back to handwritten policies.

The runner checks two permitted reads and two refused reads, asserts that the business callback ran exactly twice, and verifies that denied reads neither return bodies nor add successful-read observations. It then queries `Accessible`, explains an allowed result, and evaluates a hypothetical grant without changing real authorization. All these operations use the same generated policy.

`src/service.ts` is the porting example: an authenticated actor, a document request, trusted service-owned facts, and a business callback wrapped by `session.execute`. A deployed service must supply authentication and protect its document storage; this CLI uses fictional accounts and in-memory contents. The runtime gate cannot stop code that directly accesses storage outside this adapter.

On loading the bundle, the application pins its own `runtime.json`, checks the content hash, reparses the rules and reruns the acceptance cases. Passing those cases is not a proof of complete translation correctness. The current cases do not cover contradictory public/confidential classification; classification consistency remains an application concern.

[Generic runtime API and limits](../../runtime/README.md) · [Recorded real-model run](../../docs/application-runtime-demo.md)
