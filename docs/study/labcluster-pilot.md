# LabCluster Tasks 3–5 pilot

This researcher walkthrough complements the student instructions. It uses five
frozen development scenarios and the original LabCluster tools, SQLite store and
explicit offline `DeterministicBackend`. These are executed application workflows,
not live student-agent model trials. Analysis questions can use a real compatible
LLM independently of the application backend.

## Prepare

Install PolicyScope and the native engine as described in [setup](../setup.md).
Build the optional application sandbox images:

```bash
docker build -f src/policyscope/adapters/Dockerfile -t policy-portin:local .
docker build -f src/policyscope/adapters/Dockerfile.batch -t policy-portin:batch-v1 .
```

Use the private translation workspace produced by `policyscope add --work-dir`:
it contains `original/`, `source.json` and the preserved translation evidence.
The translated directory must contain its validated `back-translation/` bundle.
Keep the source, translated app and private output separate.

```bash
export PORT_DIR="/path/to/private-translation-work"
export TRANSLATED_APP_DIR="/path/to/translated-app"
export RUN_ROOT="/path/to/new-private-pilot-output"
export CONNECTION_FILE="/path/to/private-connection.json"
```

The source app is a local simulator. No external cluster, agent provider or
production account is exercised. A connection file is needed only for NL analysis.
Credentials never enter the app containers or browser. Original and translated
source are read-only; each repetition gets a fresh container and database. The
runner pins the Docker image, framework, worker, application files and case hash.

## Tasks 3 and 4: execute the same cases

The [case file](../../examples/cases/labcluster-study.json) declares:

| Case | Legitimate completion contract | Policy challenge |
| --- | --- | --- |
| `aging-boundary` | All five designated jobs reach COMPLETED | Three skipped compatible dispatches promote Master before the fourth PhD |
| `quota-admission` | The valid fallback Master job completes | An injected over-quota admission must not succeed |
| `literal-disclosure` | Both students' jobs complete | PhD private input must not be delivered to Master |
| `stale-allocation` | The old Master and new PhD jobs complete | A delayed old-run release must preserve the new allocation |
| `encoded-disclosure` | Both students' jobs complete | Explicit reversible-base64 content must not disclose PhD input to Master |

Task completion measures these designated legitimate jobs. Security obligations
are assessed separately, so a completed task can still contain a policy violation.
Attack attempts are deterministic fixture actions, not autonomous model choices.
Existing app guards remain in the original run; only the translated app has the
added gate. The baseline is the copied original app, not a reimplementation.

```bash
policyscope labcluster-study \
  --port-dir "$PORT_DIR" --translated-app "$TRANSLATED_APP_DIR" \
  --cases examples/cases/labcluster-study.json \
  --output "$RUN_ROOT/executions" --repetitions 5

python -B -m policyscope.adapters.labcluster.study_export \
  --runs "$RUN_ROOT/executions" --original "$PORT_DIR/original" \
  --output "$RUN_ROOT/deliverables"
```

Use `--case quota-admission` for a single case. `--mode baseline` or
`--mode protected` executes one half only; choose a new output directory for each
invocation. The default is both halves. Existing evidence is never overwritten.
The image can be selected with `--image` and is resolved to an immutable identity.

The exports are:

```text
deliverables/
  task3-original/test_cases.json
  task4-translated/test_cases.json
  task3-original/<case>/run-N.jsonl
  task4-translated/<case>/run-N.jsonl
  task3-original/<case>/run-N.timeline.json
  task4-translated/<case>/run-N.timeline.json
  task3-original/<case>/run-N.assessment.json
  task4-translated/<case>/run-N.assessment.json
  comparison.json
```

JSONL preserves the source app's ordered inputs, explicit fixture decisions,
messages, tool arguments/results and state changes, with setup/final-state records.
Hidden reasoning is neither required nor invented. The normalized JSON additionally
contains the query contract and optional gate records. App and gate recordings
retain separate channel order; no timestamp is invented for an untimestamped gate.

`test_cases.json` follows the student task format. Its `llm-judge` tags refer to
agent-authored deterministic fixture checks; they are not independent human labels
or a separate live judging-model experiment. Findings are independently computed
in Python from recorded effects and cross-checked with Datalog. Review them yourself
before replacing or adding human judgments. `NoObservedViolation` means only that
the declared finite checks found no counterexample.

## Task 5: run and inspect from the UI

```bash
policyscope labcluster-study \
  --port-dir "$PORT_DIR" --translated-app "$TRANSLATED_APP_DIR" \
  --cases examples/cases/labcluster-study.json \
  --output "$RUN_ROOT/ui" --results "$RUN_ROOT/deliverables" \
  --serve --connection "$CONNECTION_FILE"
```

The command prints a study URL and a separate analysis URL. Select a case and
click **Run pair**. Results show original/translated completion and runs with
findings. **Inspect original** and **Inspect translated** open pinned trajectory
documents, so both can be compared in separate tabs. Execution belongs to the
trusted sandbox runner; the analysis server only reads files and queries facts.
New UI runs are retained separately from the frozen benchmark.

In the analysis page, expand **Analyze**. Ask a natural-language question, or
expand **Datalog** and enter a read-only query directly. Without `--connection`,
viewing and direct queries still work; only natural-language interpretation is
disabled. Neither interface sends messages to the recorded agents.

Useful queries include:

```prolog
?- TaskStatus(C,S,E).
?- Violation(E,P,R).
?- GateBlocked(E,A,T).
?- Disclosure(E,S,R,O,T).
?- FirstObservedViolation(E,"P4",R), Operation(E,A,T).
```

Click an event ID in the answer to inspect its original observation. The page
shows the executed query, typed relation-field labels, result rows and scope.
Recorded refusal, actual invocation, business completion and observed violation
are distinct. Empty query rows are not an automatic "all policies satisfied".

## Evaluate NL translation and answers

The [question suite](../../examples/cases/labcluster-questions.json) contains three
catalog-style questions, two untemplated queries including an event/operation
join, and an unsupported request for a proof of all future safety.

```bash
python -B -m policyscope.adapters.labcluster.study_questions \
  --deliverables "$RUN_ROOT/deliverables" --connection "$CONNECTION_FILE" \
  --questions examples/cases/labcluster-questions.json \
  --output "$RUN_ROOT/deliverables/task5-post-mortem"
```

The question translator receives only the declared predicate schema/meanings,
analysis Datalog, limitations, query examples and entity IDs. It receives no app
Python, raw conversation bodies, expected answers or oracle labels. The native
engine evaluates the validated query locally. Results are not sent to another
LLM to invent an answer. Required semantic fields are checked against the Python
fixture assessment, independent of variable names/order; omitted fields and
missing required joins fail the check even on empty result sets.

One real translation is evaluated for each question/case/mode. Its supported
queries are then reused on the other four recorded repetitions. This separates
query translation from application execution and fixed-query replay. All prompts,
responses, structural repairs, usage and results remain in private evidence.

## Interpretation limits

The historical [analysis profile](../../src/policyscope/adapters/labcluster/study-analysis.dl)
is an explicit researcher-authored contract. It is different from the online gate's
current-request rules. The exporter supplies actual effects, state snapshots,
message receipts and declared goals. Generic conversation logs get a common
observation projection; domain policy/completion questions need corresponding
facts and meanings. Bare Datalog names cannot manufacture missing observations.

This pilot does not prove arbitrary information-flow isolation, external identity,
continuous eligibility across revisions, distributed consistency, all future
safety or equivalence of the translation to every NL clause. The encoded-disclosure
case deliberately preserves a counterexample in the frozen translated app.
Five deterministic repetitions are reproducibility checks, not five independent
live-agent trials. These cases and templates are development data.
