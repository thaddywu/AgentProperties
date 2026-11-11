# Policy runtime

Shared policy inference, analysis and guarded execution. Core execution has no
Grokbot, agent-framework, model or hosted-service dependency.

The primary application adapter is the [Python API](python/README.md). A `.dl`
file holds application declarations, reviewed static input facts and rules.
`Policy.execute` provides private staged EDB edits; `Policy.call` guards an existing business function; `Policy.wrap` joins an existing
host callback. LabCluster's [adaptation record](../apps/labcluster-port/ADAPTATION.md)
tracks direct tool instrumentation, the structured-report decorator and each adapter line. Both student ports
retain their original business stores; confirmed callback results incrementally update
the policy EDB without a per-call full-state projection. `.key` metadata replaces
current rows, and `InitialState(Type, State)` configures resource creation. Optional
`facts.dl` checkpoints policy facts; it does not create a shared backend transaction.

## Contract

| Layer | Relations |
| --- | --- |
| Runtime | **`Request(Q, Principal, EventKind)`**, **`Parameter(Q, Name, Value)`**, **`Allow(Q)`**, **`Deny(Q, Reason)`** |
| Optional capability | *`Capability`*, *`PrincipalGroup(Principal, Group)`*, *`ResourceGroup`*, *`Can`* |
| Optional provenance | *`Source(Principal, Data)`*, *`DependsOn(Output, Input)`*, *`Provenance(Data, Principal)`* |
| Optional FSM | *`ResourceType`*, *`ResourceState`*, *`InitialState(Type, State)`*, *`AllowedTransition`*, *`ReachableState(Type, From, To)`*, *`CanTransition`* |

Deny overrides Allow; no Allow refuses. A broad scoped Allow plus application
Deny clauses expresses default-allow authoring without a second execution API.
Principal identity is backend-bound. Resources are parameters or domain relations;
a request is not required to have one resource.

Foundation selection installs inference, not an implicit capability policy.
FSM structural checks compose with application authorization. Current state is
replaced; derived answers are recomputed. State-graph reachability is not a past
execution trace or a guarantee of a policy-authorized path.

Provenance is conservative over supplied data dependencies. No tags, sink
annotations, sanitizer, semantic-content detector or general ordering closure are
required. App-specific relations can add these semantics when needed.

## Module boundaries

- `python/policy_runtime/api.py`: small file-based application API and versioned
  data handles; low-level execution plumbing stays behind it.
- `python/policy_runtime/runtime.py`: serialized execution and pinned analysis.
- `python/policy_runtime/datalog.py`: admitted safe grammar and native Soufflé.
- `python/policy_runtime/foundations.json`: one shared foundation catalog.
- `src/application.ts`, `binding.ts`, `query.ts`, `datalog.ts`: deterministic TS
  compiler/evaluator and in-process action session; shared program identities are
  checked against Python. Backend-observed FSM execution uses Python.
- `messaging`, `backend-port`, `distributed`: optional message transport/placement
  adapters. Nova's tag-oriented example profile is separate from minimal provenance.
  Message refusal uses **`Deny(MessageRequestId, Reason)`**.
- `protocol-planner`, `bounded-equivalence`, `finite-domain`: bounded analyses with
  explicit domains and authority assumptions, not universal distributed proofs.

The admitted clause language supports positive recursion, stratified negation,
`!=` and signed 64-bit integer comparisons. It rejects arbitrary native directives,
functions, aggregates and unbounded arithmetic. Declarations are checked against
the trusted binding; reviewed static input facts cannot create request or derived
facts. Evaluation, input and output sizes are bounded.

## Execution and analysis

A real transaction or version condition must connect fact observation to the
business effect. The runtime cannot manufacture authentic facts or roll back a
remote side effect. Applied results, certified no-effect failures and uncertain
outcomes remain distinct. Uncertainty stops the session; there is no generic
reconciliation API or automatic retry.

Queries/Why/What-if use the installed program. Held snapshots do not automatically
refresh an external backend. Python capture returns a fresh pinned snapshot;
Python query returns rows, while TS additionally supports proof trees. Analysis
results are not reusable execution permits. Administrators own unrestricted query
and source access; agent tools must be scoped by the application.

Run workspace commands from the repository root:

```bash
pnpm --dir grokbot --filter @rakazo/policy-runtime check
pnpm --dir grokbot test runtime
PYTHONPATH=runtime/python python3 runtime/python/examples/quickstart.py
```
