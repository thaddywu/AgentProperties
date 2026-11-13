# Analysis

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
