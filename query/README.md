# Independent query layer

`python/policy_query` provides a read-only `QuerySession` over an explicitly captured
binding, program, input facts and optional source versions. It depends only on the
Python policy engine, not translation, evaluation, Nova or Grokbot.

- `query(source)` runs an admitted read-only query and includes snapshot identity.
- `check(intent)` previews a decision; it is not authorization to execute a callback.
- `what_if(intent, inputs)` evaluates a separate hypothetical snapshot without mutation.
- `ask(question, templates, entities, generate)` maps NL to an application-owned
  template and known entity values. Model-generated query/code is never executed.

There is no `execute` method, observation source registration, application callback,
model vendor dependency or UI. New runtime snapshots require explicit capture by
trusted application code. Decision reasons are reported as such; the Python layer
does not manufacture a full derivation proof.

```python
from policy_query import QuerySession

analysis = QuerySession(binding=binding, source=rules, inputs=captured_facts)
result = analysis.query('?- Owner(Document, Actor).')
```

Or supply a JSON file containing `binding`, `source`, `inputs` and optional `versions`:

```bash
PYTHONPATH=runtime/python:query/python python3 -m policy_query \
  /path/to/snapshot.json '?- Owner(Document, Actor).'
```

Actual queries use native Soufflé and `prlimit`. The old runtime query methods remain
compatible and share the low-level evaluator with this layer. The new application
boundary is this package; the policy engine has no reverse dependency on it.
