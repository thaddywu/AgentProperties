# Python policy adapter

The default Python API owns the policy EDB. Existing application stores and business
functions remain intact: instrument the tool/action with Policy.execute, then
write confirmed result fields inside its guarded body. No per-call full-state
projection or application snapshot producer is required.

```python
policy = Policy("rules.dl", data="facts.dl", local_effects=True)


def create(context):
    policy.put("Job", "job-1", "reader")
    return {"id": "job-1"}


result = policy.execute(subject, "create_job", {}, create)
```

`data` is optional. Without it, the EDB is in memory. With it, the runtime owns one
atomic, policy-hash-pinned checkpoint of the same facts. One active session may
write a facts file. No application database or JSON mirror is required.
For applications whose business effects are entirely EDB edits, `local_effects=True` certifies that all business effects are staged fact edits;
failed operations discard the whole batch. Use the default for real external effects,
whose uncertain outcomes stop the session rather than claiming a rollback.

## Tool annotations and caller names

Load Policy once, then annotate tool functions without a principal argument:

```python
from policyweave.enforcement import Policy, caller_context

policy = Policy("rules.dl")


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

Gate parameters and input-fact values support up to 65,536 UTF-16 code units
each; input facts retain a 4 MB aggregate value budget and native evaluation
limits. Pass only policy-relevant fields to the gate. For example,
`policy.call(actor, "submit", {"verdict": verdict}, lambda: submit(full_text))`
keeps the full business text unchanged without turning it into a policy fact.
When a policy actually needs a longer value, pass it intact within these limits;
do not truncate it to manufacture a decision. Oversized or malformed inputs are
validation errors, distinct from an evaluated policy refusal.

Existing fn(event_id) dispatchers use `@policy(name=name, arguments=args)`;
the actual trace ID is preserved while policy checks the real tool name/arguments.
MCP adapters may extract caller names from request metadata and enter caller_context;
MCP registration belongs outside the policy decorator so it registers the checked tool.
For an async function, await the decorated function; the awaited effect contract
and worker-thread hook requirements are described below.

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
before publication. No arbitrary-fact assertion tool is installed.

`policy.update(function)` is private host ingestion for real confirmations,
observations or verified evidence. It uses the same atomic input validation;
caller authentication belongs to that host boundary. A before-call adapter may
submit an actual observation such as server time. It is optional.

`@policy` also preserves async function signatures: await the decorated function
normally. For explicit intent binding use
`await policy.acall(principal, action, arguments, async_callback)`, passing the
actual original coroutine function or a `functools.partial` binding its arguments.
The original coroutine runs and is awaited on the caller's event loop; its native
gate and synchronous hooks run in a worker. The guarded fact context is available
inside the coroutine, and post-success facts publish only after it finishes.
Hooks/transactions must support the worker thread; a default thread-bound SQLite
connection cannot simply be reused. All async calls on one policy use one loop
and are serialized. Same-policy re-entry fails rather than deadlocking. Do not
hold that policy across a peer conversation that needs it for nested work; use
atomic effect boundaries and appropriate scopes. Cancellation waits for actual
coroutine cleanup, which may be delayed by an uncooperative callback; an
unconfirmed outcome remains unknown and stops the session. Async support does not
make external effects transactional or add cross-process identity guarantees.

## Shared observations

The optional `observations` mechanism supplies two host-written inputs. Referencing
one in a `.dl` rule selects the shared schemas automatically; do not redeclare them.
Alternatively select `mechanisms=("observations",)` when constructing `Policy`.

| Predicate | Meaning and storage |
| --- | --- |
| `Field(Object, Name, Value)` | An actual field or association, with set semantics. The application binding defines each name, value type, cardinality, scope and producer. |
| `Event(Id, Principal, Kind)` | A retained observation of an event, keyed by ID. Repeating the same tuple is idempotent; replacing or deleting an existing event is rejected, including through refreshed observation snapshots. |

`Request` and `Parameter` describe the current immutable intent. They remain
runtime-only and cannot be inserted as historical facts. For a confirmed call,
an `after` hook can reuse its runtime request ID:

```python
def record_read(context, result):
    request = context["request"]
    if request["event"] == "read_document":
        policy.put("Event", request["id"], request["principal"], request["event"])
        policy.put("Field", request["id"], "outcome", "applied")
        policy.put("Field", request["id"], "document", request["parameters"]["document"])
    return result


policy = Policy("rules.dl", mechanisms=("observations",), after=record_read)
```

The hook shares the guarded batch: declined or uncertain callbacks do not publish
its success facts. The result adapter must establish what confirmed success means
for the original operation. Schema selection does not install this hook, infer
success, archive every call, or capture arbitrary model/message traffic. A trusted
host can separately ingest actual failed, blocked or asynchronous observations;
an event's existence alone proves neither allowance nor success. Rules must check
the required outcome and observations explicitly. Missing events do not prove an
operation never ran. An uncertain session remains stopped; recording evidence
does not reconcile its business effects or resume execution.

Field names and quantities must refer to real data, not `Safe`, `Eligible` or
fabricated approvals. The observer may normalize units or calculate policy-independent
quantities; policy thresholds and conditional business decisions stay in rules.
No time, sequence, scope or subject column is mandatory in `Event`: record these
only when needed as explicit `Field` observations. Retain event
identities for the lifetime of the policy scope; start a new scope when retention
bounds are reached. Keeping a current `ResourceState` does not require retaining
every event or reconstructing that state from history.

Both schemas carry `hostOnly`; `FactTool` rejects exposing them to an agent.
This protects the standard agent-facing write API, not an arbitrary Python caller
already holding the trusted `Policy` object. Agent decisions use separately authorized existing application operations. Existing arbitrary read-only log
contracts retain their own schema; their events are not authenticated core facts.

Field definitions live in the optional `observation_contract`, with the same
metadata frozen by the port binding:

```python
observation_contract = {"fields": {
    "free_memory": {"type": "number", "cardinality": "one", "unit": "MB",
                    "observedAt": "memory_observed_at"},
    "memory_observed_at": {"type": "number", "cardinality": "one", "unit": "unix_ms",
                           "observedAt": None},
}}
```

The host supplies `Field(resource, "free_memory", value)` and
`Field(resource, "memory_observed_at", unix_ms)`. Units are fixed definitions,
not a column repeated on every row. Numeric values require canonical int64
encoding; malformed numbers are rejected before authorization. An `observedAt`
reference requires the timestamp field on the same object in the final snapshot.
It does not create a clock observation or automatically check freshness.
Fields declared `one` reject conflicting values; changing a value requires
removing the old tuple and inserting the new tuple in one trusted update, or
refreshing an authoritative backend snapshot. No implicit current-value upsert
is supplied. Unverified agent self-statements have no dedicated mechanism.

## Semantic boundaries for port-in

Before generating rules, describe each selected input's actual producer, authority,
object/version identity, granularity, scope, collection timing, update lifetime,
missing/invalid behavior and capture completeness. Put application-specific details
in the frozen binding plan's existing call/observation descriptions. A schema name
or a source quotation alone does not establish those semantics. Planned hooks are
not observed facts until the actual application path runs through them.

`Source(P,D)` records D's direct origin, not the truth of D or permission granted
by P. `DependsOn(Out,In)` records possible direct information influence at the
declared granularity. It does not prove which inputs a model actually used or
which private bytes an output contains. `Provenance` propagates possible origins
through the supplied graph. Absence of an origin is not evidence of clean content
when capture is incomplete. These relations cannot substitute for exact
operation/version approval bindings.

Coding agents implement dependency capture in host adapters. Runtime agents do
not choose authoritative dependency edges or remove them by self-declaration.
For model generation, connect each output to the actual supplied context and that
context to every directly supplied input, including retained history and tool
results, using version-specific IDs. Ancestors follow through the stock closure.
For deterministic copies, projections or concatenations, record the actual inputs
read by the original operation. Do not attach unrelated task history that was not
supplied. If a task-exposure node intentionally accumulates history, document it
as exposure state; do not describe it as an exact message-content dependency.

Keep content provenance and task-level obligations distinct in the binding.
Having read a web page may forbid later hiring even when the next message is a
constant. A policy's exact `done`/`failed` exception does not justify arbitrary
sanitization or runtime-agent deletion of edges. State which node and exception
each rule checks. If only coarse exposure tracking is available, preserve its
overblocking limits rather than claim exact content tracking.

`Can` and `CanTransition` are intermediate eligibility relations; final execution
still requires `Allow` and no `Deny`. Group membership is not permission. `Event`
existence is not success. Field units/types do not create measurements; timestamp
metadata does not create a clock or check freshness. Current state and configured
reachability are not execution history. Missing facts are neither zero nor proof
that something never happened. Unverified claims cannot supply these authorities.

Rule generation consumes this frozen producer meaning. Instrumentation must
implement it without silently changing granularity or scope after rules freeze.
Report missing producers, incomplete capture and incompatible exceptions as
partial/unsupported requirements or binding mismatches. Exercise the real path
with both forbidden flows and permitted flows, including inputs outside the actual
context, task separation and source-policy exceptions. Passing structural checks
does not prove complete capture or semantic equivalence.

## Decisions and foundations

- **`Request(Q, Principal, EventKind)`** and **`Parameter(Q, Name, Value)`** are bound
  to actual calls. The runtime creates Q; a backend binds the principal.
- **`Allow(Q)`** permits; **`Deny(Q, Reason)`** overrides. No Allow means refusal.
  Evaluation failure is never treated as absence of Deny.
- Optional capability: *`Capability`*, *`PrincipalGroup`*, *`ResourceGroup`*, *`Can`*.
  The module supplies inference; each app chooses how it participates in authorization.
- Optional provenance: *`Source`*, *`DependsOn`*, *`Provenance`*. Trusted tools record
  direct origins and conservative possible dependencies under an explicit producer
  contract. Tags, sanitizers and content authenticity are not automatic.
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
policy.put("ResourceType", job["id"], "job")
policy.put("ResourceState", job["id"], job["state"])
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
`completed`, `event`, `after`, `refused` and `refusal` interpret application result shapes;
`refusal(tool_name, feedback)` receives a private structured block with
`requestId`, `decision: "blocked"`, `reasonType` (`explicit_deny` or
`no_explicit_allow`) and `reasonCodes`. The trusted adapter filters reasons for
the caller and returns the app's existing error shape, or uses its established
exception protocol. This feeds the ordinary tool-result path; it does not retry
or start another agent turn. The legacy `refused(tool_name)` callback and default
`UNAVAILABLE` result remain available when no `refusal` adapter is configured.
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
managed checkpoint or host-update inputs. Real database transactions can use `sqlite_transaction`; they do not
make a remote payment or process rollbackable.

## Run and translate

Python 3.10+, Souffle 2.5 and Linux prlimit are required; Node, models and hosted
services are optional. Run workspace examples with PYTHONPATH=src or
install the root distribution with `python3 -m pip install -e .`.

[Catch Me If You Scam](../../../examples/applications/scam-port/ADAPTATION.md) documents the actual
additive tool hooks and exact upstream patches. Shared schemas/rules have one catalog;
The Python core validates reviewed bundles, including .key metadata. The earlier
TS implementation is retained in the enforcement archive.
The private worker transport is optional; managed edit handles stay in-process.
NL distillation, human assessment, coverage and rule translation remain separate
artifacts. Successful compilation is not proof of semantic equivalence.
Trusted operators may opt into private gate evidence with `Policy(..., trace=True)`
and export `policy.trajectory()`. The isolated batch runner captures the same
actual gates through `capture_trajectories()`. See the [trajectory contract](../../../docs/trajectory.md)
for required facts, effect confirmation and read-only QA. Capture does not prove
authentic identity, full mediation or business success.

# Authorized agent fact writes

`Policy.put/delete/update` are trusted host APIs. Agent connections may instead
expose `FactTool(policy, principal="arbiter", predicates=["Approval"])`, with
`register_mcp(server)` and its `system_card` added to that agent's available
interface. The host authenticates the principal; MCP arguments cannot replace it.
Use managed EDB. This tool has no business effects.

`put(predicate, values)` and `delete(predicate, values)` are separate gated actions.
Rules receive the bound principal in `Request` and the selected `predicate` plus
each declared field name in `Parameter`. Rules must grant the exact predicate,
target, issuer and values permitted by the source policy. No implicit permission
comes from exposing a predicate. Every write is checked against pre-write facts.

`put` inserts; an identical tuple is idempotent, and a different tuple with the
same declared key returns `key_conflict`. `delete` takes the complete current
tuple, so a stale decision cannot delete its replacement by reusing the key.
Deletion does not erase runtime event records. There is no agent-facing update
or atomic multi-call replacement API yet. Host `Policy.put` retains its existing
upsert semantics. Review IDs, operation content/version binding and actual review
delivery must come from the application's real lifecycle; FactTool does not
invent or distribute them. Missing integration remains a coverage gap.
