# Repository structure

```text
grokbot/                 Existing host implementation, including UI customizations
  apps/                  web, api, worker, desktop, mobile, www
  packages/              host domain/adapters/contracts/database/shared UI
  infra/                 Docker/Compose, sandbox, updater and backup services
  scripts/               Host development, deployment and demo tooling
  patches/               pnpm-applied dependency fixes
  docs/                  Host setup, operations, releases and upstream updates
apps/
  nova/
    app.md               Application specification and interaction description
    policy.md            Natural-language application requirements
    tools.md
    agents/
    episodes/            Optional examples; not part of the execution interface
    src/                 Nova application, reference rules, protocol and analyses
    tests/
runtime/                 Generic Datalog, queries, native provenance and lifecycle
translation/             One-shot natural-language-to-Datalog research prototype
  output/                Ignored local experiment artifacts
docs/                    Repository design and research documents
```

These are the five top-level source/documentation directories. Root files configure the shared pnpm workspace, CI, formatting and tests; `nova-demo.sh` is the convenience launcher. Hidden directories and ignored dependencies/local state are tooling rather than additional modules.

The dependency direction is `Grokbot UI → Nova application → policy runtime`. Translation reads an application's Markdown; its optional model adapter comes from Grokbot's existing provider-neutral connection/runtime stack. Reference policies are loaded only after model generation. Generated rules are not installed into the application.

The UI remains in Grokbot. Nova can also run without it using `pnpm --filter @rakazo/nova start`. The runtime package has no dependency on Grokbot or Nova. Nova-specific action search and local-store coordination remain with the application because their available actions, principals and protocol are domain-specific; generic evaluation/provenance live in `runtime/`.

For future student applications, this separates requirements/source code from a runtime binding. We have not defined a universal porting API, forced a coordinator/workflow, or implemented automatic source-code conversion. A future binding must identify trusted observations, actions, the enforcement point and any domain-specific analysis actions. The present Nova binding is evidence for that design, not a finalized standard.

Our application-description interface is app.md, policy.md, tools.md and agents/*.md. LLM agents document their actual system prompts; scripted agents document their actual decision logic. Episodes are optional examples, not required for translation, standalone execution or a runtime binding. The existing loader and tests accept an application without episodes/. Nova keeps two illustrative examples. Course-only submission requirements do not define the framework contract; no archives are generated. Source/README and package metadata are not required translator inputs.

## Infrastructure and patches

`grokbot/infra/compose/` builds and starts the host or the standalone Nova UI. `grokbot/infra/sandboxes/` supplies computer images and the supervisor/control service; `grokbot/infra/updater/` is the self-host update service; `grokbot/infra/systemd/` schedules backups. These are active run/deploy components, not old experiment outputs. Nova can run without the full host/sandbox stack; its Docker launcher uses `grokbot/infra/compose/Dockerfile.nova`.

`grokbot/patches/app-builder-lib@26.15.3.patch` fixes Electron's macOS signing dependency to use the keychain unlock password rather than the imported certificate password when setting key access. It is declared in root `package.json` and `pnpm-lock.yaml`; keep it until the dependency includes the fix. See [desktop release requirements](../grokbot/docs/desktop-release.md).

Current module READMEs and the design manuscript are the documentation sources. Superseded demo launch guides, archived Relay specifications, upstream marketing/changelog notes and redundant research indexes have been removed; Git history retains earlier versions.

## Rakazo updates

Grokbot preserves the upstream host's relative directory layout under one prefix. The recorded upstream baseline and [update guide](../grokbot/docs/upstream.md) provide a way to export and review subsequent upstream changes. Host changes can be applied under `grokbot/`; shared workspace configuration is reviewed separately. Policy/UI changes can still conflict, so this is a manual porting path rather than automatic synchronization.
