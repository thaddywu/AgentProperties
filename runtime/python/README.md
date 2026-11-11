# Python policy adapter

The default Python API owns the policy EDB. Existing application stores and business
functions remain intact: instrument the tool/action with Policy.execute, then
write confirmed result fields inside its guarded body. No per-call full-state
projection or application snapshot producer is required.

```python
policy = Policy('rules.dl', data='facts.dl', local_effects=True)

def create(context):
    policy.put('Job', 'job-1', 'reader')
    return {'id': 'job-1'}

result = policy.execute(subject, 'create_job', {}, create)
```

`data` is optional. Without it, the EDB is in memory. With it, the runtime owns one
atomic, policy-hash-pinned checkpoint of the same facts. One active session may
write a facts file. No application database or JSON mirror is required.
For applications whose business effects are entirely EDB edits, `local_effects=True` certifies that all business effects are staged fact edits;
failed operations discard the whole batch. Use the default for real external effects,
whose uncertain outcomes stop the session rather than claiming a rollback.

## Tool annotations and caller names

Load Policy once, then annotate synchronous tool functions without a principal argument:

```python
from policy_runtime import Policy, caller_context
policy = Policy('rules.dl')

@policy
def read_job(job_id):
    return original_read(job_id)

# At the application's dispatch point, carry its existing current agent name.
with caller_context(agent.name):
    result = read_job(job_id)
```

The decorator infers the function name and binds actual parameters. It reads the
caller when invoked; no policy file is reloaded. Missing caller names raise before
business execution. Contexts reset on exit and are isolated across threads/tasks.
This records reported names and does not authenticate them. Ordinary put/delete
calls inside the decorated body use the same staged batch.

Existing fn(event_id) dispatchers use `@policy(name=name, arguments=args)`;
the actual trace ID is preserved while policy checks the real tool name/arguments.
MCP adapters may extract caller names from request metadata and enter caller_context;
MCP registration belongs outside the policy decorator so it registers the checked tool.
Only synchronous business functions are supported by this decorator currently.

## Source and current facts

```prolog
.decl Job(Id:symbol, Owner:symbol)
.input Job
.key Job(Id)

.decl Balance(Cents:number)
.input Balance
.key Balance()
Balance(500000).

Allow(Q) :- Request(Q, P, "create_job"), PrincipalGroup(P, "Creator").
PrincipalGroup("reader", "Creator").
```

`.key` is SDK schema metadata, stripped before native Souffle execution. A put
replaces a row with the same key. An empty key means a singleton relation: updating
Balance replaces its old value. Keyed facts written in .dl are initial EDB seeds;
reopening a checkpoint does not resurrect a deleted or changed seed. Unkeyed facts
in reviewed configuration are immutable. Other unkeyed inputs use set semantics.

Inside a guarded tool, `policy.put(name, *values)` and `policy.delete(name, *key)`
join the current staged batch; they publish only after confirmed success. Outside
a tool, these calls perform a standalone trusted host update. Never expose them
as arbitrary agent/MCP fact-writing tools. `policy.rows(name)` reads staged inputs
inside a tool; `policy.transition` is its immutable selected FSM move.

The trusted effect context also exposes `facts.put(name, *values)`,
`facts.delete(name, *key)` and `facts.rows(name)`. Derived rows come from
`context['derived']`; tools do not assert them. Handles expire when the transaction
ends. Input schema, numeric types, keys and application invariants are validated
before publication. No agent/MCP arbitrary-fact assertion tool is installed.

`policy.update(function)` is private host ingestion for real confirmations,
observations or verified evidence. It uses the same atomic input validation;
caller authentication belongs to that host boundary. A before-call adapter may
submit an actual observation such as server time. It is optional.

## Decisions and foundations

- **`Request(Q, Principal, EventKind)`** and **`Parameter(Q, Name, Value)`** are bound
  to actual calls. The runtime creates Q; a backend binds the principal.
- **`Allow(Q)`** permits; **`Deny(Q, Reason)`** overrides. No Allow means refusal.
  Evaluation failure is never treated as absence of Deny.
- Optional capability: *`Capability`*, *`PrincipalGroup`*, *`ResourceGroup`*, *`Can`*.
  The module supplies inference; each app chooses how it participates in authorization.
- Optional provenance: *`Source`*, *`DependsOn`*, *`Provenance`*. Trusted tools record
  actual dependencies. Tags, sanitizers and content authenticity are not automatic.
- Optional lifecycle: *`ResourceType`*, *`ResourceState`*, *`InitialState`*, *`AllowedTransition`*,
  *`ReachableState`*, *`CanTransition`*. Existing resource type/state rows cannot be
  changed by a handler to bypass the selected transition. Creation may introduce a
  type and initial state. On confirmed success the runtime replaces ResourceState
  by resource ID; old derived answers expire on re-evaluation.

Configure a type-level initial state in the reviewed .dl file:

```prolog
// New job resources start in QUEUED; this does not reset existing resources.
InitialState("job", "QUEUED").
```

After the original create operation confirms its ID/state, the tool writes both
ResourceType and ResourceState with put in the same guarded execution. Runtime
checks new resources against InitialState before committing; existing type/state
cannot be changed by a tool outside the selected FSM transition. For example:

```python
policy.put('ResourceType', job['id'], 'job')
policy.put('ResourceState', job['id'], job['state'])
```

Other keyed app inputs use put; no manual delete is needed for replacement.
To remove an input row explicitly, use `policy.delete('Job', job_id)`. This only
deletes that fact, with no cascade or business-store mutation. An unkeyed delete
requires the complete tuple. Key replacement alone does not check an app-specific
status transition.

The request parameter selected by `target` identifies a lifecycle resource.
Keep CanTransition in the relevant Allow rules, so the policy conditions remain
readable in Datalog. Failed or merely accepted external operations must not be
reported as completed. Observed external drift requires a trusted ingestion path;
the EDB does not discover the physical world by itself.

## Execution and analysis

`Policy.execute` passes the private effect context. `Policy.call` guards a zero-argument callback; its body may write facts directly. `Policy.wrap` joins an existing callback/event protocol.
`completed`, `event`, `after` and `refused` interpret application result shapes;
`invariants` names derived relations that must stay empty. Generic staging,
key replacement and FSM commit code belongs to the SDK, not application adapters.
Keeping an original backend does not give its Store and the EDB a shared transaction.
If synchronization fails after a committed business effect, the session stops;
there is no claimed backend rollback or automatic restart reconciliation.

The admin `policy.runtime.query/check/capture/what_if` API uses the same facts and
rules. Its optional `snapshot()` returns EDB rows for analysis/export; an application
is not required to implement snapshot(). A business view tool can serialize scoped
query results for an existing UI or agent. It is not a second state authority.

For an existing external backend, the optional `facts(context, data)` observation
profile still supplies complete current relations. It cannot be combined with a
managed checkpoint or host-update inputs. This profile is not required by either
student port. Real database transactions can use `sqlite_transaction`; they do not
make a remote payment or process rollbackable.

## Run and translate

Python 3.10+, Souffle 2.5 and Linux prlimit are required; Node, models and hosted
services are optional. Run workspace examples with PYTHONPATH=runtime/python or
install with `python3 -m pip install ./runtime/python`.

[LabCluster](../../apps/labcluster-port/ADAPTATION.md) and
[Catch Me If You Scam](../../apps/scam-port/ADAPTATION.md) document the actual
additive tool hooks and exact upstream patches. Shared schemas/rules have one catalog;
TS and Python independently validate reviewed bundles, including .key metadata.
The private worker transport is optional; managed edit handles stay in-process.
NL distillation, human assessment, coverage and rule translation remain separate
artifacts. Successful compilation is not proof of semantic equivalence.
