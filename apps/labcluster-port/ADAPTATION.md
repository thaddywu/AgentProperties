# LabCluster: additive tool instrumentation

Read the [enforcement guide](../../src/policyscope/enforcement/README.md), then rules.dl in
P1.1-P6.7 order. All app clauses have short English explanations.

## Original code retained

Baseline [repository](https://github.com/CeciliaTheBirb/CS239_LabCluster_QianxunXu),
revision `c5ca03d0cc35651fa49c8d637074e8258a1a715e`. The MIT notice is preserved.
The patch is applied only to a temporary checkout.

upstream.patch instruments the original tool branches directly. For example:

```python
elif name=='submit_job':
    @policy(name=name, arguments=a)  # Adaptation code: read caller at invocation.
    def fn(e):
        result=s.submit(r,a['spec'],e)  # Original Store operation.
        # Adaptation code: stage only the confirmed job fields.
        if result.get('ok') is not False:
            job=result['job']
            policy.put('ResourceType', job['id'], 'job')
            policy.put('ResourceState', job['id'], job['state'])
            policy.put('Job', job['id'], job['owner'], job['version'], job['task_hash'], job['run_id'])
            # ... other returned fields; all assignments are explicit in upstream.patch.
        return result
```

The original dispatch branch now annotates its callback:

```python
@policy(name=name, arguments=a)
def fn(e):
    ...  # Original Store operation plus explicit policy.put calls above.
```

The annotation has no principal parameter. The original callback only receives a
trace event ID, so name/arguments identify the real tool request.

Caller extraction is application adaptation, kept in adapter.py. The added
@caller_from_tools on original Tools.call reads tools.role and supplies that name
to @policy internally. The original Trace.tool call is unchanged. Developers do
not manage a caller_context block at the tool's business-code boundary.

When Trace invokes fn(action), @policy automatically creates Request/Parameter,
checks Allow/Deny and runs the body only if permitted. Explicit put/delete calls
stage EDB updates; the SDK validates and commits after confirmed success. Policy
is loaded once at startup. Caller extraction reads a name, without authenticating it.

Submit/revise write Job and its returned fields directly. Approval writes its
three relations directly. Dispatch records the actual Run, Node, Job and Waiting
deltas directly. Only repeated receipt and terminal-release assignments
remain shared helpers in tool_facts.py. Provenance writes are explicit at each
recording site: data.reference obtains an ID, RecordData maps the business record,
and Source/DependsOn records the origin/dependency. Each call is next to the operation it records.

The `Adaptation code:` prefix identifies inserted code; new helper modules carry
that prefix in their module docstrings. Original Store business methods remain unchanged.

core/messaging.py adds an import and this decorator; Bus.send's body is unchanged:

```python
@guard_completion_reports(ApplicationError)  # Adaptation code: authorize before delivery.
def send(self, sender, recipient, kind, body, parents=(), origin='application'):
    ...  # Original body.
```

The wrapper checks COMPLETION_REPORT with the host-supplied sender and copied
body.job_id before trace or inbox effects. A denial raises the original application
error. Successful calls retain the original received-event ID. Other message kinds
remain outside this guard; free-text semantics are not classified.

The composition root creates Store and calls its original initialize, then adds
`store.policy = adapt()`. Original Tools construction, agents, Scenario, schema
validation, ROLE_TOOLS, scheduler, Store snapshots and Trace remain unchanged.
Snapshots used by original business/trace code are not Datalog input producers.

## File responsibilities

| File | Responsibility |
| --- | --- |
| rules.dl | Policy inputs, keys, English-annotated rules, InitialState and FSM edges |
| adapter.py | Load policy once, interpret event/result shapes and read the existing Tools.role caller name |
| tool_facts.py | Shared receipt and terminal-result assignments, with explicit provenance puts; no event dispatcher, Store reads or business execution |
| message_adapter.py | Gate structured completion-report ownership before original delivery; preserve return/error shapes |
| run.py | Compose original Store/agents/scenario with the optional policy attachment |
| upstream.patch | Tool annotations, caller-name hook, explicit fact writes and message decorator; Store retained |
| src/policyscope/enforcement/ | Caller contexts, tool annotations, shared staging, keys, FSM commit and validation |

The previous operations.py business reimplementation has been removed. EDB is
policy evidence; original Store remains the business authority.

## Every nonblank adapter line

| Line | Code | Meaning |
| --- | --- | --- |
| 1 | `"""Adaptation code: load one policy scope and interpret original tool events/results."""` | State the application adapter responsibility. |
| 3 | `from pathlib import Path` | Locate the reviewed policy file. |
| 4 | `from functools import wraps` | Preserve original function metadata. |
| 5 | `from policyscope.enforcement import Policy, caller_context` | Import the runtime and its internal caller-name carrier. |
| 8 | `def caller_from_tools(function):` | Adapt the original Tools dispatcher. |
| 9 | `"""Adapt the caller name already held by the original Tools instance."""` | Document the existing role as the name source. |
| 10 | `@wraps(function)` | Keep the original call signature and metadata. |
| 11 | `def call(tools, *args, **kwargs):` | Receive the original Tools instance and call arguments. |
| 12 | `with caller_context(tools.role):` | Read tools.role and carry that name during this dispatch. |
| 13 | `return function(tools, *args, **kwargs)` | Run the original Tools.call; its annotated callback performs enforcement. |
| 14 | `return call` | Return the adapted dispatcher. |
| 17 | `def adapt(*, bundle=None):` | Create one policy scope, optionally with a reviewed bundle. |
| 18 | `return Policy(` | Construct the shared Policy instance. |
| 19 | `Path(__file__).with_name('rules.dl'), bundle=bundle,` | Load declarations, initial facts, keys and rules. |
| 20 | `target='job_id', invariants=('AllocationViolation',),` | Select the FSM resource argument and allocation postcondition. |
| 21 | `event=lambda name, args: 'reject_job' if name == 'approve_job' and args.get('approve') is False else name,` | Map approve=False to the job-rejection event. |
| 22 | `completed=lambda result: result.get('ok') is not False,` | Treat explicit ok=False as an unapplied operation. |
| 23 | `refused=lambda name: {'status': 'UNAVAILABLE'} if name == 'read_job' else {'ok': False, 'code': 'UNAVAILABLE'},` | Preserve original refusal result shapes. |
| 24 | `)` | Finish the policy configuration. |

## Actual result flow

The guarded callback checks the actual bound request, then runs the instrumented tool branch.
On ok=false it publishes no fact delta. On success the tool and shared helpers record only
returned IDs, version/spec/approval/run/receipt fields and affected deltas.
Read results never refresh the EDB. There is no cluster_facts or source callback.

Original submit returns the created ID/state; the tool puts ResourceType and
ResourceState directly. At commit, runtime checks each new resource against the
reviewed InitialState("job", "QUEUED"). Existing resource state cannot be reset by
a tool. Other current fields use .key plus put; delete removes a row by that key.
Original lifecycle results confirm the selected target; the runtime updates
policy ResourceState after validation.

For the pinned cluster, one node exists per type. Returned run.candidate_order
identifies the actual competing jobs whose Waiting deltas are recorded. A backend
with different scheduling effects needs a faithful explicit change record, not
an assumed generic mapping. No framework builtin contains this app detail.

## Boundaries

Store and EDB do not share a transaction. A post-effect mapping/invariant failure
stops the scope and discards staged policy edits; it cannot undo an already
committed Store operation. This is checked explicitly. The adapter uses the
SDK default external-effect semantics.

The demo uses a fresh Store and policy scope. Restart/reconciliation, unobserved
drift, full message/context/export isolation and the original injected unsafe
T4 direct callback remain outside the guarded tool boundary. The structured
completion-report gate does not establish general P2 message isolation. Host role strings
are the original demo convention, not implemented login authentication.

## Run

```bash
PYTHONPATH=src python3 apps/labcluster-port/run.py --upstream /path/to/pinned-checkout
PYTHONPATH=src python3 apps/labcluster-port/tests/verify.py --upstream /path/to/pinned-checkout
PYTHONPATH=src python3 apps/labcluster-port/tools/build_artifacts.py
```

Adapter SHA-256: `f11db45bed5a687c8a830c0c3831205011902baf223fc063396eba5800a64660`

Patch SHA-256: `82cb206fb85d8137bd17e13d8fe37a304543497433c37e0d1456079267fc7e87`
