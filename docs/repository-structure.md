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
examples/
  quickstart/        Small runnable integration
  applications/      App adapters and reviewed reference policies
  cases/             Synthetic data-only comparison inputs
docs/                Framework guides and archive recovery
  study/             Study protocol, student guides and illustrations
  research/          Optional manuscript submodule
pyproject.toml       One installable Python distribution and command catalog
```

`core` owns the one rule parser/evaluator, schemas, fixed foundations and decision semantics. Enforcement and analysis reuse it. The five modules do not import Grokbot or Nova. Domain predicates and business effects remain application-owned; LabCluster's specialized controller and runner live in `adapters/labcluster`, not the generic policy adder.

Back-translation consumes actual rules, input meanings, configuration and implementation evidence. Source policy and forward plans stay out of that model session. The viewer's separate alignment pass may read source policy and frozen descriptions; it cannot rewrite those descriptions. The adder's existing roundtrip composes the modules while preserving this input separation.

The workbench owns the HTTP server, static UI and study records. Browser code expresses intent and renders state. Trusted backend code chooses application runners, files, model connections and sandbox adapters. Public HTTP requests cannot choose executable connector paths or credentials.

`analysis/timeline.py` validates data-only participant/message/tool logs and adapts
existing gate logs for viewing. `workbench/analysis.py` and `static/analysis.*`
provide the independent read-only UI through `policyscope inspect`. It has no
application runner, message sender or model connection.

Analysis has no business-execution authority. It accepts explicit snapshots and
versioned gate trajectories containing exact rules, per-decision input facts and
confirmed outcomes. Full snapshots preserve captured deletions and replacements;
arbitrary transcripts cannot supply missing facts automatically. The
[trajectory contract](trajectory.md) describes the interface and trust limits.
Proof-tree parity and application action search remain future work.

`workbench/pipeline.py` composes the five modules through `policyscope pipeline`.
It owns orchestration and private evidence; application predicates and adapters
remain outside this generic composition.

Model generation is injected. The compatible HTTP model transport and coding-agent/Docker integration are optional; their SDKs and credentials do not enter core semantics. New app adapters must establish identity, authoritative facts, actual effect boundaries and independent tests. Existing synchronous/local contracts do not claim distributed transactions or complete mediation of an arbitrary app.

Maintenance tools live with their owner: `python -B -m tests` runs verification, `policyscope.adapters.install_souffle` installs the optional native engine, and `docs/study/build_pdf.py` builds the student guide. There is no separate scripts directory.

Default private runtime state lives under `~/.local/state/policyscope`; disposable outputs live under `~/.cache/policyscope`. `XDG_STATE_HOME` and `XDG_CACHE_HOME` can select other roots. Local historical backups are outside the checkout. Archive branches retain the previous host, TypeScript code and public experiment artifacts. There is one active development branch, `master`; the five `archive/*` module branches are frozen references.
