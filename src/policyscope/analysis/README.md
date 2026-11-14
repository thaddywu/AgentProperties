# Analysis

`policyscope inspect trajectory.json` opens the read-only frontend. It accepts
conversation/tool logs with declared participants and existing gate trajectories;
it requires no model, native engine or running app. See the
[timeline contract](../../../docs/timeline.md). Messages, arguments and results
remain data; the viewer has no recorded-agent send or execute interface.

`LogQuerySession` follows the archived question workflow through Python components:

- `translation.py`: `QuestionTranslator` selects a question template and known
  entity parameters, then compiles a read-only query. Questions outside the catalog
  can still produce an admitted custom query, clarification or unsupported result.
- `log_query.py`: prepares a plan bound to the immutable trajectory and executes
  its query through the shared native evaluator.
- `answers.py`: fills fixed answer text with exact result rows. There is no answer
  generation model call. Counts, evidence links, empty results and scope are retained.

In the UI, choose **Use template** for an offline example, or enter a question and
click **Translate**, inspect the plan, then **Run analysis**. Query details and raw
rows are expandable. The Datalog editor remains available for direct queries.

```python
from policyscope.analysis.log_query import LogQuerySession
from policyscope.analysis.timeline import Timeline

session = LogQuerySession(Timeline(recorded_json))
plan = session.translate(question, generate)  # no fact evaluation
answer = session.answer(plan)                # deterministic query + answer
# Or: session.prepare(template_id, parameters), without any model.
```

`ask(question, generate)` retains the one-call composition. The model sees schema
meanings, rules, scope, template definitions and entities, without application
code, raw facts or answer wording. Generic logs get observation templates; domain
questions need an explicit fact producer and analysis profile. Old three-field
query examples remain compatible and use the generic answer template. Start the
viewer with `--connection` for optional natural-language interpretation.

`QuerySession` performs read-only analysis over an explicitly captured binding, rule source, input facts and optional source versions. It depends on `core`, without execution callbacks or application imports.

```python
from policyscope.analysis import QuerySession

session = QuerySession(binding=binding, source=rules, inputs=captured_facts)
result = session.query("?- Owner(Document, Actor).")
```

- `query(source)` returns admitted query rows and snapshot identity.
- `check(intent)` previews a decision; it does not authorize execution.
- `what_if(intent, inputs)` evaluates an isolated hypothetical input state.
- `ask(question, templates, entities, generate)` selects an app-owned query template and known entities. Model-generated code is never executed.

`policyscope analyze snapshot.json '?- Owner(D, A).'` reads JSON containing `binding`, `source`, `inputs` and optional `versions`. Actual evaluation needs native Soufflé and `prlimit`.

`TrajectorySession` accepts versioned captured gate trajectories, replays their
decisions, queries exact per-event fact snapshots and supports generic bounded NL
QA. It does not need to import the app or know its predicates in advance. Use
`policyscope analyze trajectory.json --verify` for deterministic replay, or
`--question 'Why was the first call blocked?' --connection connection.json` for QA.

See the [trajectory contract](../../../docs/trajectory.md) for capture, required
facts, outcomes, trust limits and the composed five-module command. Raw transcripts
need a trusted evidence adapter. Archived proof trees and action search are not
claimed as Python capabilities.
