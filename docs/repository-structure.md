# Repository structure

```text
src/policyweave/
  policy_adder/       NL requirements/rules and isolated application adaptation
  back_translation/  Independent rules/implementation reading
  policy_viewer/     Literal source units and frozen-description alignment
  enforcement/       Online gate, effect outcomes and staged fact updates
  analysis/          Read-only captured-state analysis
  core/              Shared schema, rule semantics, compilation and artifacts
  adapters/          Optional models and isolated execution workers
  workbench/         Shared HTTP/UI composition and study persistence
tests/               Offline and headless browser tests
runs/                Ignored local workspaces; one timestamped directory per app run
examples/
  quickstart/        Small runnable integration
  applications/      App adapters and reviewed reference policies
  cases/             Synthetic data-only comparison inputs
docs/                Current framework guides and documentation index
  design/            Observation contracts and staged port workflow
  phase2-hw-release/ Overleaf Git submodule for merged course instructions
  course/            Course landing page and reproducible publication tool
  research/          Optional manuscript submodule
pyproject.toml       One installable Python distribution and command catalog
install.sh           Optional translation setup; native tools live in adapters
```

`core` owns the one rule parser/evaluator, schemas, fixed foundations and decision semantics. Enforcement and analysis reuse it. The five modules do not import Grokbot or Nova. Domain predicates, business effects and application runners remain application-owned.

Back-translation consumes actual rules, input meanings, configuration and implementation evidence. Source policy and forward plans stay out of that model session. The viewer's separate alignment pass may read source policy and frozen descriptions; it cannot rewrite those descriptions. The adder's existing roundtrip composes the modules while preserving this input separation.

The workbench owns the HTTP server, static UI and study records. Browser code expresses intent and renders state. Trusted backend code chooses application runners, files, model connections and sandbox adapters. Public HTTP requests cannot choose executable connector paths or credentials.

Its `port` and `back-translate` commands compose the existing adder, independent
reader and alignment contracts. `workbench/runner.py` only captures and exports
an episode as JSON/JSONL around student-owned execution and completion callbacks; it cannot
supply app scenarios or change their criteria. Student scenario and completion code remain protected across original and ported
applications. App runtime/model/tool/transport modules remain instrumentation targets.
`workbench/translate_harness.py` adapts a single original Python harness through
the shared model connection, preserves helper/checker definitions, and adds the
shared CLI for APP_DIR selection, recording and reporting. It does not edit or
execute either app during translation. The execution callback receives the episode
directory for intermediate files.
After each run command, the runner scans all current single-field `result.json`
files and prints cumulative task-completion counts for both app sides. Framework
execution/capture diagnostics stay separate in `run.json`.
The isolated runtime snapshot includes the shared runner without the HTTP/UI code.

`analysis/timeline.py` validates data-only participant/message/tool logs and adapts
existing gate logs for viewing. `workbench/analysis.py` and `static/analysis.*`
provide the independent read-only UI through `policyweave inspect`. It has no
application runner or message sender. `analysis/log_query.py` validates optional
data-only analysis contracts and bounded NL-to-Datalog queries. `analysis/translation.py`
owns question interpretation and template compilation; `analysis/answers.py` owns
deterministic answer rendering. Domain question/answer templates are data in app
adapters. The optional
analysis model receives schema, meanings, rules and scope, without app code or
raw event bodies. `workbench/experiment.py` composes a separate execution UI with
a trusted registered runner and independent assessment criteria.

Analysis has no business-execution authority. It accepts explicit snapshots and
versioned gate trajectories containing exact rules, per-decision input facts and
confirmed outcomes. Full snapshots preserve captured deletions and replacements;
arbitrary transcripts cannot supply missing facts automatically. The
[trajectory contract](trajectory.md) describes the interface and trust limits.
Proof-tree parity and application action search remain future work.

`workbench/pipeline.py` composes the five modules through `policyweave pipeline`.
It owns orchestration and private evidence; application predicates and adapters
remain outside this generic composition.

Model generation is injected. The compatible HTTP model transport and coding-agent/Docker integration are optional; their SDKs and credentials do not enter core semantics. New app adapters must establish identity, authoritative facts, actual effect boundaries and independent tests. Existing synchronous/local contracts do not claim distributed transactions or complete mediation of an arbitrary app.

`adapters/model_settings.py` safely loads private connection YAML, selects its
`openai`, `anthropic` or `codex-compatible-local-endpoint` section and validates
only the selected connection for use. The local profile requires explicit
endpoint/model settings and reuses Chat Completions plus Codex/Responses;
`auto` only selects hosted profiles.
`adapters/compatible.py` selects Chat Completions or native Messages;
`adapters/messages.py` owns Messages wire translation. `adapters/coding.py`
selects Codex or Claude Code under the same isolated session contract, while
`adapters/model_proxy.py` keeps credentials on the host and restricts the model
and protocol routes. Port stages, frozen artifacts and review formats stay owned
by the existing modules. No vendor SDK is required by the Python distribution.

Maintenance tools live with their owner: `python -B -m tests` runs verification and `policyweave.adapters.install_souffle` installs the optional native engine. Course documents live in the `docs/phase2-hw-release` Overleaf submodule; [documentation setup](README.md) covers its local connection and the one-command CS239-Phase2 release in `docs/course/publish.py`. There is no separate scripts directory.

`install.sh` prepares the local Python environment and execution images.
`adapters/install_tools.py` reuses compatible native CLIs or downloads pinned,
checksum-verified releases into the user cache, then links tools into the Python
environment. Model credentials remain separate in the shared connection YAML.

Create application workspaces from the repository root with `policyweave new-run APP`.
Each empty `runs/YYYYMonDD_HHMM_APP/` directory holds that run's original app,
port, harness, results, review, report and costs. Names use local time; same-minute
collisions receive a numeric suffix. Git and Docker build contexts exclude the
entire `runs/` tree. Generated harnesses retain relative application and fixture
paths so a complete workspace can move together. Historical local evidence can
be retained under `runs/_archive/`; Git archive branches retain older code.

Default shared runtime state lives under `~/.local/state/policyweave`; disposable
tool caches live under `~/.cache/policyweave`. `XDG_STATE_HOME` and `XDG_CACHE_HOME`
can select other roots. There is one active development branch, `master`; the
five `archive/*` module branches are frozen references.

## Historical implementations

The complete pre-restructure snapshot is tagged `archive/pre-restructure-2026-11-12`; the first consolidated Python layout is `archive/python-layout-2026-11-12`. Frozen branches `archive/policy-adder`, `archive/back-translation`, `archive/policy-viewer`, `archive/enforcement` and `archive/post-mortem` each retain their runnable context and `ARCHIVE.md`. Earlier branch tips are tagged under `archive/branches-2026-11-12/*`.

These archives contain the previous host, TypeScript runtimes, Nova proof trees/action search and historical public experiment artifacts. Active imports use `policyweave.*`; the earlier `policy_runtime`, `policy_translation`, `policy_query` and `policy_evaluation` roots remain archived. Private prompts, source copies, connection settings and raw logs are excluded from publication.

```bash
git fetch origin --tags
git show origin/archive/post-mortem:ARCHIVE.md
git tag --list 'archive/branches-2026-11-12/*'
git worktree add --detach /path/to/archive origin/archive/post-mortem
```
