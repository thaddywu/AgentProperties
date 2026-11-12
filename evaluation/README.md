# Independent policy evaluation

Run from the repository root with Python 3.10 or newer:

```bash
python3 evaluation/run.py
```

Open **http://127.0.0.1:5190**. No Node, pnpm, Grokbot, Docker, database or model is
needed to review the reference. Actual policy execution and snapshot queries use
native **Soufflé 2.5** and Linux `prlimit` on PATH; the existing
[runtime setup](../runtime/python/README.md) describes that engine.

The default application is a small scripted document backend. The original run
really reads a synthetic document; the protected run executes the same callback
through the policy runtime. Its two reference policies are developer-authored,
not model output or study results. Scenario controls determine this example's
operation; the task text records the student's intent. An agent-backed connector
can instead use that task to drive its own agent.

To review the existing LabCluster artifacts independently:

```bash
python3 evaluation/run.py --review-app apps/labcluster-port \
  --port 5191 --data evaluation/output/labcluster
```

This imports 41 requirements and 30 reference readings with checked hashes. It
supports the Review page; it does **not** pretend to supply an RQ3 runner
for LabCluster. A stale reference is rejected.

For a new model-generated port with actual LabCluster execution, use the
[agentic port-in workflow](porting/README.md). It inspects the original source,
generates a mapper and rules, tests and repairs them, then connects an accepted
candidate through `--ported-app`. This profile uses Docker isolation and includes
an RQ3 runner; the legacy `--review-app` import remains review-only.

## Student review

The review combines RQ1 and RQ2. The unchanged policy is highlighted in source
order, with Previous/Next and a sentence dropdown. Categories and fidelity ratings
sit side by side below the source, with back-translation on the right. Other accepts
a custom name. Changes autosave;
incomplete explanations remain visibly unsaved and prevent navigation. Execution
descriptions use short business sentences covering permissions, conditions and
refusals. Input origins expand only when needed. The original sentence and generic
execution titles are not repeated on the right. A version selector appears only
when multiple reviews exist. Descriptions never replace executable policy.

Test-file execution is separate from the review UI. Run Original and Protected
comparisons from the command line; the backend retains trajectories and judgments
for export. There is no Results page or generic application-control form.

```bash
python3 evaluation/run_cases.py --cases evaluation/examples/document-tests.json \
  --data evaluation/output/file-tests
# For an accepted port (Docker required):
python3 evaluation/run_cases.py --ported-app evaluation/output/my-port \
  --cases evaluation/examples/labcluster-tests.json --data evaluation/output/port-tests
```

Use a separate result directory from any running server. The JSON format is
`{"version": 1, "cases": [...]}`; each case supplies `id`, `task`, `setup` and
`expected`, with optional `seed` (42) and `split` (`development`). All cases are
validated before any run. Files are data, never executable commands. `setup` is
validated by the installed application runner; this file format does not provide
an arbitrary backend with reset/instrumentation automatically. For the scripted
examples, `setup` selects actual behavior and `task` records intent, not a model
prompt. Expected outcomes never become automatic human judgments.

For an existing port, generate the new execution reading separately:

```bash
python3 evaluation/review_port.py --ported-app evaluation/output/my-port \
  --connection /path/to/private-connection.json
```

The first pass sees rules, adapter and relevant implementation evidence, with no
original policy or forward plan. A separate pass links the frozen descriptions
to literal policy sentences. Bounded validation repairs check rule coverage and
exact evidence quotations; they do not prove semantic equivalence or accurate
alignment. `execution-review.json` pins both passes to the original review and
artifacts. Restarting the workbench adds this as a new review version, retaining
old ratings separately. Detailed attempts and measured usage stay private.

`study.json` and Export retain pinned sentence offsets, judgments and revisions,
custom categories, run evidence and completion judgments. Sentence counts are
reported separately from legacy requirement counts; they are not adjudicated
atomic-requirement denominators. Existing review hashes and older judgments are
preserved. Port artifacts remain in the separate port output directory.

This entry point still selects the trusted application at server startup.
For a local student checkout, the optional [Codex port launcher](porting/README.md)
adds Translate and Back-translate to the same panel. The operator selects the
repo/connection once with `--repo` or `--codex-port`; HTTP never accepts executable
paths or credentials. Reverse reading and sentence alignment are separate
sessions, and results are saved. A new backend still needs its own RQ3 connector.

## Packages and boundaries

| Package | Source | Owns |
| --- | --- | --- |
| `policy-runtime` | `runtime/python/` | Fact ownership, trusted action gate, native Datalog execution |
| `policy-translation` | `translation/python/` | Requirements, shared rules, mappings and independent back-translation |
| `policy-query` | `query/python/` | Read-only snapshots, questions and hypothetical decisions |
| `policy-evaluation` | `evaluation/` | Student records, experiment orchestration, local HTTP API and static UI |

Translation and query depend on the policy engine. They do not depend on each
other, evaluation, Nova or Grokbot. The policy engine does not import them.
Evaluation composes the three through a trusted application adapter. UI files live
only in `evaluation/policy_evaluation/static/`; they render state and submit intent.
The historical TypeScript/Nova paths remain compatible; they are not dependencies
of this Python stack. Legacy runtime query methods delegate to the same low-level
engine primitive, avoiding a second query evaluator.

For installation outside the checkout, create a virtual environment and install
all four local distributions together:

```bash
python3 -m venv .venv
.venv/bin/pip install ./runtime/python ./translation/python ./query/python ./evaluation
.venv/bin/policy-evaluate --data evaluation/output/study
```

The runtime dependencies are standard-library Python plus the native engine;
setuptools is a build dependency. `policy-translate`, `policy-query` and
`policy-evaluate` are separate entry points. The checkout launcher only adds the
four package locations to Python's import path.

## Model connection

An operator may supply the existing generic connection shape in a **private** JSON
file outside the repository:

```json
{
  "baseUrl": "https://MODEL-ENDPOINT.example/v1",
  "modelId": "MODEL_ID",
  "apiKey": "YOUR_API_KEY",
  "maxTokens": 12000
}
```

```bash
python3 evaluation/run.py --connection /path/to/private-connection.json
```

The optional adapter uses standard chat completions. The core accepts any injected
`generate(stage, prompt)` callable, including a local model. No vendor is required.
Credentials stay server-side. Model settings and executable connector code cannot
be submitted through the UI. There is no reference fallback on provider failure.

Open a `.txt` or `.md` document, or paste unnumbered text, and select Translate.
Each new review is immutable; prior reviews and human judgment histories remain.
The source is preserved with Unicode code-point spans. PDF/Word extraction and
automatic source-code instrumentation are not implemented.

Back-translation receives the actual rules, bound input meanings, fixed foundations
and configuration, without the original policy or requirement statements. Every
rule must map to source requirements. Omitted source text becomes a visible gap.
One structural repair per stage is permitted and recorded; a gap-only draft is
`requirements-only`, not a completed rule/back-translation run. Drafts are never
installed by rating them. Model classification, compilability and human ratings
are three different observations, not interchangeable evidence of correctness.

## Study and runners

[STUDY.md](STUDY.md) defines the student tasks, denominators and current limits for
RQ1–3. Coverage and Translation store judgments against immutable review and
requirement IDs. Runs stores scenarios, separate development/held-out labels,
paired trajectories and human outcome judgments. Export includes versioned records
and counts, retaining unknown, failed and unreviewed cases.

Application integration implements [ApplicationAdapter](policy_evaluation/contracts.py).
Select trusted code at startup, for example:

```bash
policy-evaluate --application my_application.evaluation:Application \
  --data evaluation/output/my-study
```

The connector must reset state independently for each run, preserve original guards,
change only the added policy mediation between modes, and emit actual boundary
observations. Its result includes `completed`, `initialStateHash` and
`configurationHash`; unequal initial-state/configuration hashes mark a pair
non-comparable. These are adapter attestations, not a proof of complete mediation.
Record model/version/settings and measured token usage when a model is used.
`setup_fields` defines supported scenario controls; `validate_setup` owns validation.
Run code must be bounded and return failures explicitly; this local synchronous
runner does not sandbox arbitrary code or supervise remote jobs.

Each pair records the **installed** policy hash and origin. The initial connector
uses a developer reference, even after a student creates a new translation draft.
Testing a candidate requires a trusted connector to load that separately validated
candidate and a fresh study directory. General automatic porting and an agentic
adapter generator are future work.

The server binds to loopback, checks Host/Origin and requires a per-start token for
mutations. It is a local single-user workbench, not a deployed multi-user service.
Private study data and model attempts live in ignored `evaluation/output/` with
restricted file permissions. Do not put real credentials in student documents.

## Verification

```bash
python3 evaluation/check.py
# Optional browser-test dependencies, not application dependencies:
python3 -m pip install -r evaluation/requirements-test.txt
python3 -m playwright install chromium
python3 evaluation/tests/ui_smoke.py
```

Without Soufflé, native tests skip; with it, tests exercise real allowed/blocked
callbacks, isolated hypothetical queries, persistence, failures and HTTP boundaries.
The browser tests use synthetic model output and cover review navigation, saving,
version switching and translation controls. Screenshots are saved
under `evaluation/test-results/`; offline integration tests cover native execution.
CI runs this stack without installing the Grokbot workspace.
