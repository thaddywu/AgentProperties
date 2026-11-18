# Trajectory evidence and application boundaries

For the **read-only frontend**, use the [timeline contract](timeline.md): one JSON
file declares participants, directed messages, tool calls/results and optional
state. Start Inspector with the shared connection YAML for QA; the original app
does not need to be running.
`policyweave inspect` also opens the richer gate logs defined below. This page's
rules-and-facts requirements apply to decision replay and policy QA, rather than
to browsing an ordinary conversation/tool trajectory.

The five modules share interfaces, rather than a fixed application vocabulary. The low-level API permits application-owned actors, actions, predicates and fact keys;
the default port-in profile generates no new EDB or IDB schema. A port
must connect those declarations to real identity, authoritative observations and
the original business callbacks. Passing one application's tests does not prove
that another application's boundaries are complete.

| Module | Generic input and output | Application integration required |
| --- | --- | --- |
| Policy adder | Clean source checkout + application description + NL policy → instrumented app, rules, tests | Supported dependencies and executable offline scenarios; generated changes need review |
| Back-translation | Frozen implementation, rules and bindings → independently generated execution descriptions | Readable implementation evidence; original NL policy and forward plans are excluded from this pass |
| Policy viewer | Original NL policy + frozen descriptions → sentence alignment and judgments | Source documents and validated reference artifacts; alignment is not an equivalence proof |
| Enforcement | Declared rules + current facts + authenticated request + callback → decision and confirmed outcome | Trusted identity/fact mapping, complete mediation, and honest effect confirmation |
| Analysis | Versioned trajectory containing exact policy and facts → replay, queries, hypotheticals and bounded NL QA | Trusted capture or conversion of original logs into the evidence contract below |

Currently executable adaptation uses the optional Python/Docker coding adapter.
Other source languages can be copied and read, but arbitrary runtimes, native
dependencies, distributed transactions and remote services are not automatically
supported. External services may use explicit offline fixtures during experiments;
these do not establish production integration or policy fidelity.

## Capture

The [student runner](porting.md#student-runner) uses the same scenarios and
completion checker for original and ported applications. Original runs need no
trajectory. A ported run exports a conversation/tool timeline (`trajectory.jsonl` and `trajectory.json`)
and exact gate recordings (`gate-N.json`), independently of task completion.

| Run artifact | Schema |
| --- | --- |
| `result.json` | Exactly `{"task_complete": true}` or `{"task_complete": false}` |
| `run.json` | Framework diagnostics: `version: 1`, `side`, `case`, `sample`, `executionStatus` (`completed` or `failed`), nullable Boolean `taskCompleteness`, `trajectories` (relative filenames), optional `errorType` |
| `trajectory.json` | `format: "policyscope-timeline"`, `version: 1`, `title`, `roles`, ordered `events`; event kinds include messages, tool calls/results, visible `llm_output` and captured state |
| `trajectory.jsonl` | One metadata/participant header, followed by the same ordered events, one per line |
| `gate-N.json` | `format: "policyscope-trajectory"`, `version: 1`; exact installed policy, gate inputs, decisions and outcomes, defined below |

The historical `policyscope-*` wire identifiers remain unchanged for compatibility.
Files live in `OUTPUT/CASE/SIDE/sample-N/`, which already identifies the case,
app side and positive sample index. The student's single task verdict is true
when actual effects and final responses match the expected outcome. False also
covers an execution error or timeout that prevents confirming completion. Keep the
same checker for both sides; a gate verdict does not establish task completion.

After every run command, the shared CLI scans all current result files at that
path shape and prints completed/total samples separately for original and ported.
It counts files, not scenarios or planned samples; earlier results in the same
output directory are included. Directories without a result file do not count.
Only the Boolean `task_complete` field is accepted. The summary contains task
completion only.

`run.json` holds framework diagnostics separately. Execution/capture status can
fail while retaining a true task verdict if assessment finished before capture
failed. A missing assessment stays null in these diagnostics and yields false
in `result.json`. Exception text is omitted; `errorType` records only its type.

These files are private run artifacts. `result.json` is an assessment record;
open its timeline with `policyweave inspect --traj FILE.jsonl --connection connection.yaml`.
The same command accepts `FILE.json`. Use the private connection file prepared for
translation so trajectory review includes QA.

The student harness supplies execution and actual-effect completion checks. Port-in
installs observation hooks; the shared runner owns export. Native gate evidence is
embedded with policy identity and explicit `callId`, so Inspector can resolve
parameters, verdicts and facts without a per-app converter. `Policy.trajectory()`
exports one policy runtime, while `recording.export(directory)` exports an episode.

Trusted host code can opt into recording on an ordinary gate:

```python
policy = Policy("rules.dl", trace=True)
# Invoke the application's normal policy.call(...) paths.
trajectory = policy.trajectory()
```

An isolated test runner can instead use `capture_trajectories()` around application
import and execution, then export its collected recorders. Neither option replaces
the runtime, callbacks or native evaluator. Capture is private and opt-in because
facts, parameters and callback results can contain sensitive data. Do not expose
the admin export to an untrusted application agent or commit real trajectories.

The generic batch runner exports `policyTrajectories` and `trajectoryCoverage`.
An incomplete recorder or oversized export is explicitly incomplete. The composed
pipeline requires complete evidence and exact replay before reporting success.

## Version 1 contract

`TrajectorySession(value)` is the executable validator. Unknown header/event fields
are rejected. JSON uses these fields:

| Header field | Required value |
| --- | --- |
| `format`, `version` | `"policyscope-trajectory"`, `1` |
| `traceId`, `id` | Bounded session identifier; content fingerprint |
| `policy` | Exact `binding`, rule `source`, installed policy `hash` |
| `initialInputs` | Complete initial input facts as `{predicate, args: [strings]}` |
| `scope` | Recorder's observation and confirmation limits |
| `events` | Ordered events, at most 1,000 per session |

Each event has `kind`, distinct `id`, contiguous integer `sequence`, `hash`,
`inputs`/`inputHash`, `committedInputs`/`committedInputHash`, and `outcome`.

For `kind: "call"`, `request` binds the event ID to its actor, action, parameters
and optional resource. `inputs` is the complete input state available to the gate
after preparation and observation refresh, excluding runtime request relations.
The exact `request` supplies those immutable request/parameter rows through the
shared evaluator during replay, fact retrieval and gate queries.
`observationVersions` records available
source versions. `decision` records the actual policy result; `effectCalled`
records whether the real callback was invoked. An applied callback can include
`result` and `resultHash`. Outcomes distinguish:

- `blocked`: the gate refused and the callback was not invoked.
- `applied`: the trusted adapter confirmed application; this alone does not prove business success.
- `not_applied`: the adapter confirmed no application, including discarded local edits.
- `unknown`: an effect may have happened; no rollback or committed facts are certified.
- `failed`: the gate could not complete; a missing decision remains unresolved.

For `kind: "update"`, the trusted host records complete before/after fact snapshots
and a `source` trust qualification. It does not manufacture an agent action.
Failed updates do not certify a successful update event.

These are snapshots, not a union of historical facts. Deletions, changed ownership,
revoked approvals and externally refreshed facts must be reflected in the next
gate snapshot. Missing facts cannot be recovered from prose with certainty. A raw
chat/tool log needs a trusted converter that supplies this information; absent
evidence must remain unavailable. One trace binds one installed policy.

Hashes detect changed artifacts; they do not authenticate the recorder. A forged
but internally consistent log can pass replay. The format describes mediated gates;
it cannot certify actions taken through uninstrumented channels or reconstruct an
unprotected application's violations without additional observation evidence.

## Read-only QA

Conversation/tool timelines now also support a data-only historical analysis
contract and NL-to-Datalog in the [read-only viewer](timeline.md). Historical
analysis rules can differ from online current-request gate rules: they need
recorded effects, identities, state changes and declared task goals. The
application supplies that contract and independent assessment criteria. App Python is not needed by
the query translator; predicate meanings, units, evidence producers and scope
still are. A transcript or bare predicate name cannot certify missing facts.

```python
from policyweave.analysis import TrajectorySession

session = TrajectorySession(trajectory)
verification = session.verify()
answer = session.run({"operation": "decision", "eventId": event_id})
answer = session.ask("Why was this call blocked?", generate)
```

`verify()` re-evaluates each captured decision with the same native engine. Empty
traces are not successful replay; unresolved gates are reported separately.
`run()` admits only `overview`, `events`, `decision`, `facts`, `changes`, and
`what_if`. QA cannot import application code, call business callbacks or execute
model-generated queries/code. It supports application-declared predicates without
an app-specific question catalog. Hypotheticals change an isolated fact copy.

NL QA first selects an admitted operation, then interprets its deterministic
result. Exact event references are checked. Prose is still model interpretation,
not a checked semantic proof; retain the result and scope beside the answer. A
question without sufficient evidence can return a clarification.

```bash
policyweave analyze trajectory.json --verify
policyweave analyze trajectory.json --question 'Why was the first call blocked?' --connection /path/to/private-connection.yaml
```

## Compose all five modules

```bash
policyweave pipeline /path/to/base-app /path/to/enforced-app \
  --work-dir /path/to/private-work \
  --connection /path/to/private-connection.yaml \
  --policy policies.md --app-doc app.md --image policy-portin:batch-v1
```

The source must be a clean Git checkout; output/work directories stay outside it.
The command adapts the app, checks the published app without authoring policies,
independently reads the implementation, validates the viewer bundle, replays all
captured decisions, and runs three generic QA questions. `--question` customizes
the questions. A completed matching port may use `--reuse-port` with a new target;
the summary labels reuse and still reruns publication checks and QA. Private
evidence and module status are retained on failure. The summary does not claim
semantic equivalence, complete mediation or full parity with archived proof-tree
and action-search experiments.
