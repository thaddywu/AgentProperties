# Policy workspace

A workspace for multi-agent applications, policy enforcement, sensemaking queries and natural-language policy translation.

The student workbench now runs independently of Grokbot:

```bash
python3 evaluation/run.py                 # http://127.0.0.1:5190
```

See [the independent stack](../evaluation/README.md) for installation, model connections
and LabCluster review, and [RQ1–3](../evaluation/STUDY.md) for student tasks and study
limits. Reviewing the reference needs only Python; actual enforcement and queries
also need native Soufflé and `prlimit`.

| Directory | Responsibility |
| --- | --- |
| [grokbot/](../grokbot/README.md) | Host implementation and web/Electron/mobile UI |
| [apps/](repository-structure.md) | Nova plus the independent [Document Vault](../apps/document-vault/README.md) app and runtime binding |
| [runtime/](../runtime/README.md) | Policy layer: trusted action gate, facts and Datalog engine; standalone Python plus TS compatibility |
| [translation/](../translation/README.md) | Translation layer: independent Python requirements/rules/back-translation; historical TS experiments |
| [query/](../query/README.md) | Query layer: read-only snapshots, questions and hypothetical checks |
| [evaluation/](../evaluation/README.md) | Independent student UI, study records and paired experiment orchestration |
| [docs/](repository-structure.md) | Repository design and research documents |

Application descriptions use `app.md`, `policy.md`, `tools.md` and `agents/`. LLM agents supply their actual system prompts; scripted agents describe their decision logic. Episodes are optional examples.

## Run

Run commands from the repository root. The Python student stack needs no host installation.
For the existing Nova/Grokbot host, use the Node version and pnpm declared in
`grokbot/package.json`, then install with `pnpm --dir grokbot install --frozen-lockfile`.

```bash
./apps/nova/run.sh                         # Grokbot UI + Nova; Docker required
pnpm --dir grokbot policy:review            # Policy review UI; no Docker or model required for the reference
pnpm --dir grokbot --filter @rakazo/nova start        # Nova without UI; Soufflé + prlimit required
pnpm --dir translation translate ../apps/nova --connection /path/to/private-connection.json
```

See [Nova setup and commands](../apps/nova/README.md), [model connections](../translation/README.md), and [full Grokbot host setup](../grokbot/docs/self-host.md).

`grokbot/infra/` contains active Docker/Compose, sandbox, updater and backup tooling. `grokbot/patches/` contains the pnpm-applied Electron signing dependency fix; neither directory is an archive.

[App → translation → runtime walkthrough](../apps/document-vault/README.md) · [Repository boundaries](repository-structure.md) · [Translation experiments](translation-model-comparison.md) · [Research design submodule](research/) · [Contributing](../.github/CONTRIBUTING.md) · [Security](../.github/SECURITY.md) · [Apache 2.0 license](LICENSE)

The manuscript lives in the `docs/research` Git submodule. Initialize it with `git submodule update --init --recursive` when working on the paper; access to the paper repository is required. Core application commands do not require it. Edit `docs/research/main.tex`; the root `main.tex` is a local compilation entry point. Commit and push manuscript changes inside the submodule before committing the updated submodule revision in this repository.

[Application porting contract](application-porting-contract.md) defines backend-independent adapters, builtin IFC/capability/FSM mechanisms, policy and execution declarations, and trusted EDB producers. The Python API owns the policy EDB: original business stores remain intact, confirmed tool-result hooks stage fact updates, and keys replace old current values without a per-call full-state projection. It specifies the implemented TypeScript message/FSM ports, readable primitives, source bindings and remaining durable/remote deployment work. [Nova's runtime inventory](nova-runtime-contract.md) maps that boundary to Nova predicates and protocol placement.

[File-based Python adapters](../runtime/python/README.md) guard existing business calls. Core requests have a principal and event kind; optional foundations provide group permissions, unlabelled provenance and typed resource state. Numeric comparisons are evaluated directly. [LabCluster adaptation record](../apps/labcluster-port/ADAPTATION.md) tracks the exact upstream patch and every adapter line.

[Python adapter guide](../runtime/python/README.md) starts with a runnable offline
example and a standalone Python/Soufflé runtime, without Node or Grokbot.
[LabCluster port](../apps/labcluster-port/README.md) exercises the original student
backend with per-rule/predicate coverage and explicit unmediated message/context
requirements. Generic translation now separates NL distillation, a pinned developer
assessment and shared-rule translation; unsupported clauses remain in the report.

[Distributed protocol synthesis RQ](distributed-protocol-rq.md) describes query-style placement/transfers and a bounded study of storage, communication and inference costs. Nova's Rules dialog presents runtime, app inputs, translated extensions, reference rules/protocol and actual prevention. The equivalence target is the union of local closures plus decision behavior at every location; the current checker supplies snapshot evidence, not a universal proof.

[Nova evaluation pilot](nova-evaluation-pilot.md) records independent porting experiments and initial evidence for expressiveness, translation accuracy and end-to-end safety/task completion, with offline replay and explicit study limits.

[Three-RQ lab](../apps/nova/evaluation/README.md#three-rq-lab-observable-equality-and-measured-model-usage) provides exact positive-UCQ fragment checks, recursive observable comparisons, and a small real routing-model experiment with provider-reported token counts. The manuscript has a separate Evaluation Plan section.

[Bounded SAT and configurable testing](../apps/nova/evaluation/README.md#bounded-sat-and-configurable-testing) now compare full stratified recursive programs over explicit finite input catalogs, with replayable counterexamples, seeded/exhaustive EDB tests and real port traces.

[PolicyScope guide](policyscope-guide.pdf) is the single English PDF: Section 1.1
covers all runtime/analysis builtins and gate semantics; Section 1.2 starts with
a minimal adapter API table and direct instrumentation in the original tool. Sections 2 and 3
walk through the original policies of LabCluster and Catch Me If You Scam, followed
by each application's unsupported and conditional scope.

Rebuild from reviewed source files:

```bash
PYTHONPATH=runtime/python python3 docs/guides/build_policy_walkthrough.py
```
