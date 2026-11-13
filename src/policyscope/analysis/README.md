# Analysis

`policyscope inspect trajectory.json` opens the read-only frontend. It accepts
conversation/tool logs with declared participants and existing gate trajectories;
it requires no model, native engine or running app. See the
[timeline contract](../../../docs/timeline.md). Messages, arguments and results
remain data; the viewer has no recorded-agent send or execute interface.

`LogQuerySession` adds a separate interface for data-only timelines: direct
read-only Datalog or optional NL-to-Datalog over a declared analysis contract.
Queries may extend beyond templates. The model sees schema meanings, rules,
scope, examples and entities, without application code or raw fact rows. Native
evaluation returns exact rows locally. Generic logs get a fixed observation
projection; domain policy/completion questions require an explicit fact producer
and analysis profile. Unsupported questions remain unsupported. Start the viewer
with `--connection` to enable this optional analysis model.

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
