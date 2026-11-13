# Repository structure

```text
src/policyscope/
  policy_adder/       NL requirements/rules and isolated application adaptation
  back_translation/  Independent rules/implementation reading
  policy_viewer/     Literal source units and frozen-description alignment
  enforcement/       Online gate, effect outcomes and staged fact updates
  analysis/          Read-only captured-state analysis
  core/              Shared schema, rule semantics, compilation and artifacts
  adapters/          Optional models, sandboxing and LabCluster profile
  workbench/         Shared HTTP/UI composition and study persistence
tests/               Offline and headless browser tests
apps/                Python application adapters and reviewed reference policies
examples/            Small runnable integrations
evaluation/          Data-only experiment cases
scripts/             Verification and documentation tools
docs/                Guides, archive index and optional manuscript submodule
pyproject.toml       One installable Python distribution and command catalog
```

`core` owns the one rule parser/evaluator, schemas, fixed foundations and decision semantics. Enforcement and analysis reuse it. The five modules do not import Grokbot or Nova. Domain predicates and business effects remain application-owned; LabCluster's specialized controller and runner live in `adapters/labcluster`, not the generic policy adder.

Back-translation consumes actual rules, input meanings, configuration and implementation evidence. Source policy and forward plans stay out of that model session. The viewer's separate alignment pass may read source policy and frozen descriptions; it cannot rewrite those descriptions. The adder's existing roundtrip composes the modules while preserving this input separation.

The workbench owns the HTTP server, static UI and study records. Browser code expresses intent and renders state. Trusted backend code chooses application runners, files, model connections and sandbox adapters. Public HTTP requests cannot choose executable connector paths or credentials.

Analysis has no business-execution authority. Its current input is an explicit snapshot (`binding`, `source`, `inputs`, optional `versions`), not an arbitrary chat transcript. Historical trajectory reconstruction, fact revocation semantics, proof-tree parity and application action search remain future work. The archived Nova implementation documents the richer TS experiment.

Model generation is injected. The compatible HTTP model transport and coding-agent/Docker integration are optional; their SDKs and credentials do not enter core semantics. New app adapters must establish identity, authoritative facts, actual effect boundaries and independent tests. Existing synchronous/local contracts do not claim distributed transactions or complete mediation of an arbitrary app.

`output/`, `backups/`, test artifacts, environments and credentials are ignored and private. Archive branches retain the previous host, TypeScript code and public experiment artifacts. There is one active development branch, `master`; the five `archive/*` module branches are frozen references.
