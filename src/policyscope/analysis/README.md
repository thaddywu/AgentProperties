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

This is the current Python foundation of post-mortem analysis. Arbitrary trajectory ingestion, historical fact deletion/revocation reconstruction and full proof trees are not implemented. Nova's richer TS analyses remain in `archive/post-mortem`; see [migration limits](../../../docs/archives.md).
