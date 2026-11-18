# Analysis

`policyweave inspect --traj trajectory.jsonl --connection connection.yaml` opens
the read-only frontend with QA configured. It accepts
conversation/tool logs with declared participants and existing gate trajectories;
use the same private connection YAML as translation for the standard Inspector
workflow. The original app need not be running. See the
[timeline contract](../../../docs/timeline.md). Messages, arguments and results
remain data; the viewer has no recorded-agent send or execute interface.

In the Inspector's **QA** tab, select a recorded tool call and choose one of four
fixed questions: **Why blocked?** (or **Why allowed?**), **Access control**,
**Information flow**, or **Effects**. Click **Analysis**. The backend owns the
catalog and accepts only its preset IDs; the HTTP interface rejects free text.
`call_analysis.py` verifies native decision replay and evaluates the verdict and
supporting queries against the exact before snapshot. Decision and access-control
questions query concrete role, ownership or state conditions as well as verdicts.
The model proposes bounded supporting queries and explains their native result
rows; it cannot replace the recorded verdict. Effects use the paired tool result
and exact confirmed before/after changes; missing state remains unknown.
Information-flow questions inspect recorded origins and dependencies when present
and explicitly retain missing-evidence limits otherwise. The UI displays query
rows and the event citation; **Translation and query** expands all queries and
replay status. Permission, callback execution and task completion remain distinct.
A blocked read does not prove the entire run avoided disclosure.
Model explanations should be assessed against the displayed evidence; matching
decision replay verifies the verdict, not every sentence of the explanation.

`LogQuerySession` provides a separate Python question workflow:

- `translation.py`: `QuestionTranslator` selects a question template and known
  entity parameters, then compiles a read-only query. Questions outside the catalog
  can still produce an admitted custom query, clarification or unsupported result.
- `log_query.py`: prepares a plan bound to the immutable trajectory and executes
  its query through the shared native evaluator.
- `answers.py`: fills fixed answer text with exact result rows. There is no answer
  generation model call. Counts, evidence links, empty results and scope are retained.

```python
from policyweave.analysis.log_query import LogQuerySession
from policyweave.analysis.timeline import Timeline

session = LogQuerySession(Timeline(recorded_json))
plan = session.translate(question, generate)  # no fact evaluation
answer = session.answer(plan)  # deterministic query + answer
# Or: session.prepare(template_id, parameters), without any model.
```

`ask(question, generate)` retains the one-call composition. The model sees schema
meanings, rules, scope, template definitions and entities, without application
code, raw facts or answer wording. Generic logs get observation templates; domain
questions need an explicit fact producer and analysis profile. Old three-field
query examples remain compatible and use the generic answer template. This
Python/CLI workflow is separate from the Inspector's fixed-question HTTP API.

`QuerySession` performs read-only analysis over an explicitly captured binding, rule source, input facts and optional source versions. It depends on `core`, without execution callbacks or application imports.

```python
from policyweave.analysis import QuerySession

session = QuerySession(binding=binding, source=rules, inputs=captured_facts)
result = session.query("?- Owner(Document, Actor).")
```

- `query(source)` returns admitted query rows and snapshot identity.
- `check(intent)` previews a decision; it does not authorize execution.
- `what_if(intent, inputs)` evaluates an isolated hypothetical input state.
- `ask(question, templates, entities, generate)` selects an app-owned query template and known entities. Model-generated code is never executed.

`policyweave analyze snapshot.json '?- Owner(D, A).'` reads JSON containing `binding`, `source`, `inputs` and optional `versions`. Actual evaluation needs native Soufflé and `prlimit`.

`TrajectorySession` accepts versioned captured gate trajectories, replays their
decisions, queries exact per-event fact snapshots and supports generic bounded NL
QA. It does not need to import the app or know its predicates in advance. Use
`policyweave analyze trajectory.json --verify` for deterministic replay, or
`--question 'Why was the first call blocked?' --connection connection.yaml` for QA.

See the [trajectory contract](../../../docs/trajectory.md) for capture, required
facts, outcomes, trust limits and the composed five-module command. Raw transcripts
need a trusted evidence adapter. Archived proof trees and action search are not
claimed as Python capabilities.
