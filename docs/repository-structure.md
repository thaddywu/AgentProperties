# Repository structure

```text
grokbot/                 Existing host implementation, including UI customizations
  AGENTS.md              Host/client-specific development rules
  apps/                  web, api, worker, desktop, mobile, www
  packages/              host domain/adapters/contracts/database/shared UI
  config/                Workspace test configuration
  infra/                 Docker/Compose, sandbox, updater and backup services
  scripts/               Host development, deployment and demo tooling
  patches/               pnpm-applied dependency fixes
  docs/                  Host setup, operations, releases and upstream updates
  package.json           Workspace commands and shared development tools
  pnpm-workspace.yaml    Host and adjacent application/runtime package membership
  pnpm-lock.yaml         Preserved dependency resolutions
  node_modules/          Ignored dependency installation
apps/
  document-vault/         Independent app, trusted runtime binding and gated document service
  nova/
    app.md               Application specification and interaction description
    policy.md            Natural-language application requirements
    tools.md
    agents/
    episodes/            Optional examples; not part of the execution interface
    src/                 Nova application, reference rules, protocol and analyses
    tests/
    run.sh               Docker/UI entry point, invoked from the repository root
runtime/                 Generic action gate, Datalog, queries, provenance and lifecycle
translation/             One-shot natural-language-to-Datalog research prototype
  output/                Ignored experiments and validated policy bundles
docs/                    README, LICENSE, repository design and research documents
```

The repository root contains the five module/documentation directories plus `AGENTS.md` and `CLAUDE.md` for coding-agent instructions. Project files live with their owner:

| Location | Contents |
| --- | --- |
| `docs/README.md`, `docs/LICENSE` | Workspace introduction and preserved Apache license |
| `grokbot/package.json`, `grokbot/pnpm-workspace.yaml`, `grokbot/pnpm-lock.yaml`, `grokbot/.npmrc` | Installation, scripts, package membership and locked dependency versions |
| `grokbot/node_modules/` | Ignored installation output |
| `grokbot/config/`, module `biome.json` files | Tests and module-scoped formatting |
| `runtime/tsconfig.base.json` | Shared TypeScript settings |
| `apps/nova/run.sh` | Nova UI entry point |

The host workspace explicitly includes adjacent `../apps/*`, `../runtime` and `../translation` packages. Use `pnpm --dir grokbot ...` from the checkout root. Recursive pnpm build/check commands replace Turbo, which does not support workspace packages outside its root. `repository-command.mjs` keeps repository-wide CLI file paths relative to the checkout while resolving tools from the host installation. Vitest caches also stay under the host installation. Formatting runs separately inside the host, Nova, runtime and translation modules, avoiding local state outside those module roots. Each module points formatting at the Git root and force-ignores private debug state and translation output; see [Biome configuration](https://biomejs.dev/reference/configuration/#vcsroot).

Only `.gitignore`, `.gitattributes` and `.dockerignore` remain as tracked root dotfiles: they govern repository-wide exclusion/line endings and the root Docker build context. `.github/` contains CI, platform screenshots/releases, issue templates and contribution/security guidance. GitHub workflow discovery requires that location. `.agents/` contains coding-assistant skills (`composio`, `pr-watch`); these are development helpers. Application agent specifications live in `apps/*/agents/`. The root `AGENTS.md` holds repository-wide rules; `grokbot/AGENTS.md` adds host/client rules. `CLAUDE.md` imports the root rules. Local private debug state is ignored and is separate from the module layout.

The dependency direction is `Grokbot UI → Nova application → policy runtime`. Translation reads an application's Markdown; its optional model adapter comes from Grokbot's existing provider-neutral connection/runtime stack. The generic translation path emits a validated policy bundle which an app explicitly loads through `createPolicySession`. Document Vault runs actual callbacks through that gate and uses the same policy for query/Why/What-if. The legacy whole-policy Nova experiment remains comparison-only. The new Nova extension path supplies the fixed foundation and protocol to the model, compares generated extensions against golden behavior, and exports artifacts that Nova can explicitly install into fresh sessions.

The UI remains in Grokbot. Nova can also run without it using `pnpm --dir grokbot --filter @rakazo/nova start`. The runtime package has no dependency on Grokbot or Nova. Its `messaging-policy` export supplies the fixed IFC/capability rule foundation and input schemas; Nova composes those with its five app-specific reference rules. Nova-specific action search and local-store coordination remain with the application because their available actions, principals and protocol are domain-specific; generic evaluation/provenance live in `runtime/`. Extracting the foundation does not yet supply a generic distributed transport adapter or protocol-plan compiler; see the [protocol synthesis proposal](distributed-protocol-rq.md).

For student applications, the first generic porting interface now accepts an adapter-owned runtime binding, a translated bundle, trusted observations and an action callback. The [runtime SDK](../runtime/README.md) supplies execute/check/query/why/whatIf; [Document Vault](../apps/document-vault/README.md) is an independent example. Its `runtime.json` describes actual instrumentation and acceptance cases; it can also be supplied separately with `--binding`, so it does not redefine student Markdown requirements. Automatic source instrumentation, distributed transactions, persistent generic sessions and general prevention/completion planning remain unimplemented.

Our application-description interface is app.md, policy.md, tools.md and agents/*.md. LLM agents document their actual system prompts; scripted agents document their actual decision logic. Episodes are optional examples, not required for translation, standalone execution or a runtime binding. The existing loader and tests accept an application without episodes/. Nova keeps two illustrative examples. Course-only submission requirements do not define the framework contract; no archives are generated. Source/README and package metadata are not required translator inputs.

## Infrastructure and patches

`grokbot/infra/compose/` builds and starts the host or the standalone Nova UI. `grokbot/infra/sandboxes/` supplies computer images and the supervisor/control service; `grokbot/infra/updater/` is the self-host update service; `grokbot/infra/systemd/` schedules backups. These are active run/deploy components, not old experiment outputs. Nova can run without the full host/sandbox stack; its Docker launcher uses `grokbot/infra/compose/Dockerfile.nova`.

`grokbot/patches/app-builder-lib@26.15.3.patch` fixes Electron's macOS signing dependency to use the keychain unlock password rather than the imported certificate password when setting key access. It is declared in `grokbot/package.json` and `grokbot/pnpm-lock.yaml`; keep it until the dependency includes the fix. See [desktop release requirements](../grokbot/docs/desktop-release.md).

Current module READMEs and the design manuscript are the documentation sources. Superseded demo launch guides, archived Relay specifications, upstream marketing/changelog notes and redundant research indexes have been removed; Git history retains earlier versions.

The [application porting contract](application-porting-contract.md) owns the target boundary between policies, optional builtin/FSM configuration, execution protocols and trusted EDB producers. `docs/research/main.tex` is the canonical manuscript. The root `main.tex` is its standalone Overleaf export; regenerate that copy from the canonical source instead of editing both independently. Neither the illustrative contract format nor protected resource FSM execution is implemented by the current version-1 binding.

## Rakazo updates

Grokbot preserves the upstream host's relative directory layout under one prefix. The recorded upstream baseline and [update guide](../grokbot/docs/upstream.md) provide a way to export and review subsequent upstream changes. Host changes can be applied under `grokbot/`; shared workspace configuration is reviewed separately. Policy/UI changes can still conflict, so this is a manual porting path rather than automatic synchronization.

Nova now keeps Covered local and computes Finished only in the global observer. The observer runs completion rules on the union of local closures, never local enforcement rules. Audit-summary transport has been removed; saved translation experiments are historical and retain their original protocol.
