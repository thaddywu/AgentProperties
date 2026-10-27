# Policy workspace

A workspace for multi-agent applications, policy enforcement, sensemaking queries and natural-language policy translation.

| Directory | Responsibility |
| --- | --- |
| [grokbot/](../grokbot/README.md) | Host implementation and web/Electron/mobile UI |
| [apps/nova/](../apps/nova/README.md) | Nova specification, policies, agents/tools, source and tests |
| [runtime/](../runtime/README.md) | Shared Datalog evaluation, queries, provenance and lifecycle relations |
| [translation/](../translation/README.md) | One-shot natural-language-to-Datalog prototype |
| [docs/](repository-structure.md) | Repository design and research documents |

Application descriptions use `app.md`, `policy.md`, `tools.md` and `agents/`. LLM agents supply their actual system prompts; scripted agents describe their decision logic. Episodes are optional examples.

## Run

Run commands from the repository root. Use the Node version and pnpm declared in `grokbot/package.json`, then install with `pnpm --dir grokbot install --frozen-lockfile`.

```bash
./apps/nova/run.sh                         # Grokbot UI + Nova; Docker required
pnpm --dir grokbot --filter @rakazo/nova start        # Nova without UI; Soufflé + prlimit required
pnpm --dir grokbot policy:translate apps/nova --connection /path/to/private-connection.json
```

See [Nova setup and commands](../apps/nova/README.md), [model connections](../translation/README.md), and [full Grokbot host setup](../grokbot/docs/self-host.md).

`grokbot/infra/` contains active Docker/Compose, sandbox, updater and backup tooling. `grokbot/patches/` contains the pnpm-applied Electron signing dependency fix; neither directory is an archive.

[Repository boundaries](repository-structure.md) · [Translation experiments](translation-model-comparison.md) · [Research design](research/main.tex) · [Contributing](../.github/CONTRIBUTING.md) · [Security](../.github/SECURITY.md) · [Apache 2.0 license](LICENSE)
