# Policy workspace

A workspace for multi-agent applications, policy enforcement, sensemaking queries and natural-language policy translation.

| Directory | Responsibility |
| --- | --- |
| [grokbot/](../grokbot/README.md) | Host implementation and web/Electron/mobile UI |
| [apps/](repository-structure.md) | Nova plus the independent [Document Vault](../apps/document-vault/README.md) app and runtime binding |
| [runtime/](../runtime/README.md) | Generic action gate, Datalog evaluation, queries, provenance and lifecycle relations |
| [translation/](../translation/README.md) | One-shot translation and validated runtime bundles |
| [docs/](repository-structure.md) | Repository design and research documents |

Application descriptions use `app.md`, `policy.md`, `tools.md` and `agents/`. LLM agents supply their actual system prompts; scripted agents describe their decision logic. Episodes are optional examples.

## Run

Run commands from the repository root. Use the Node version and pnpm declared in `grokbot/package.json`, then install with `pnpm --dir grokbot install --frozen-lockfile`.

```bash
./apps/nova/run.sh                         # Grokbot UI + Nova; Docker required
pnpm --dir grokbot --filter @rakazo/nova start        # Nova without UI; Soufflé + prlimit required
pnpm --dir translation translate ../apps/nova --connection /path/to/private-connection.json
```

See [Nova setup and commands](../apps/nova/README.md), [model connections](../translation/README.md), and [full Grokbot host setup](../grokbot/docs/self-host.md).

`grokbot/infra/` contains active Docker/Compose, sandbox, updater and backup tooling. `grokbot/patches/` contains the pnpm-applied Electron signing dependency fix; neither directory is an archive.

[App → translation → runtime walkthrough](../apps/document-vault/README.md) · [Repository boundaries](repository-structure.md) · [Translation experiments](translation-model-comparison.md) · [Research design submodule](research/) · [Contributing](../.github/CONTRIBUTING.md) · [Security](../.github/SECURITY.md) · [Apache 2.0 license](LICENSE)

The manuscript lives in the `docs/research` Git submodule. Initialize it with `git submodule update --init --recursive` when working on the paper; access to the paper repository is required. Core application commands do not require it. Edit `docs/research/main.tex`; the root `main.tex` is a local compilation entry point. Commit and push manuscript changes inside the submodule before committing the updated submodule revision in this repository.

[Application porting contract](application-porting-contract.md) defines backend-independent adapters, builtin IFC/capability/FSM mechanisms, policy and execution declarations, and trusted EDB producers. It specifies the implemented TypeScript message/FSM ports, readable primitives, source bindings and remaining durable/remote deployment work. [Nova's runtime inventory](nova-runtime-contract.md) maps that boundary to Nova predicates and protocol placement.

[Distributed protocol synthesis RQ](distributed-protocol-rq.md) describes query-style placement/transfers and a bounded study of storage, communication and inference costs. Nova's Rules dialog presents runtime, app inputs, translated extensions, reference rules/protocol and actual prevention. The equivalence target is the union of local closures plus decision behavior at every location; the current checker supplies snapshot evidence, not a universal proof.

[Nova evaluation pilot](nova-evaluation-pilot.md) records independent porting experiments and initial evidence for expressiveness, translation accuracy and end-to-end safety/task completion, with offline replay and explicit study limits.
