# Application adaptation contract

An application keeps its agent framework and tool boundary. It may use the runtime EDB as its sole business authority, or explicitly connect an external backend. The policy
adapter connects real effects to a reviewed Datalog program. The [LabCluster
adaptation record](../apps/labcluster-port/ADAPTATION.md) gives the exact original
revision, complete patch, every adapter line and policy coverage boundaries.

## What an application supplies

1. Relation declarations and policy clauses in one `.dl` file. Static configuration,
   including typed FSM edges, may be declared as reviewed input facts in that file.
2. The meaning and producer of application inputs. Facts may come from an existing
   business query, stored state, confirmed operation result or observer. The runtime
   does not assume every backend has a reader or a default world state.
3. A real business callback. `Policy.call` or `Policy.wrap` checks before invoking
   it. The authenticated principal is supplied by the backend.
4. A transaction or version boundary appropriate to the actual effects. Result
   interpretation and output projection remain explicit application semantics.

The SDK handles declaration parsing, shared schemas, request IDs, inference,
decisions, immutable callback context and data-handle allocation. An application
must not copy those mechanisms into its adapter. Field mappings and business
result conventions cannot be inferred by the SDK.

## Minimal vocabulary

**`Request(Q, Principal, EventKind)`** and **`Parameter(Q, Name, Value)`** describe the
captured call. Resources are ordinary parameters or domain relations, supporting
zero or multiple targets. **`Allow(Q)`** permits, subject to every **`Deny(Q, Reason)`**.
A policy may supply a broad Allow and specific denial clauses. Missing required
observations and evaluator failures are errors, not proof that Deny is absent.

Capability membership and resource scopes are optional. *`Can`* is derived from
explicit grants and declared memberships; selecting the module never forces
capability-based authorization on every app. PrincipalGroup argument order is
member first, group second.

Provenance uses Source, DependsOn and Provenance over version-specific data IDs.
The direct edge records possible dependency; the closure conservatively preserves
origins. Labels, allowed recipients and release exceptions are app policy. Removing
private fields does not automatically erase provenance.

FSM configuration includes *`InitialState(Type, State)`* and
*`AllowedTransition(Type, EventKind, Before, After)`*. A confirmed creation writes
ResourceType and ResourceState with put in the same tool batch. Runtime validates
new resources against InitialState; tools cannot reset existing lifecycle state.
ResourceType binds instances to shared edges; ResourceState represents current
state under the application's authority contract. CanTransition matches current
state, while ReachableState is type-level structural reachability. No mandatory
execution-history, enabled-action, known-resource or recovery relations exist.

## Facts and effects

The default file-based API owns one EDB. Trusted tool result hooks write staged input facts
through Policy.wrap/call/execute; the runtime validates and publishes the complete batch.
There is no required application Store or full snapshot-to-facts callback. .key
metadata declares automatic replacement, including singleton current values. The
shared ResourceState key is the resource ID. Failed operations publish no edits;
confirmed FSM effects replace current state in the same commit.

Optional facts.dl persistence checkpoints the same EDB atomically, pins the reviewed
policy hash and permits one active writer. It is not a distributed transaction or
remote-effect recovery protocol. local_effects=True is only for effects entirely
inside the EDB. Existing business stores can remain unchanged: an after hook records the confirmed
result delta without a full source projection. Its commit is not automatically
atomic with the policy EDB; uncertain post-effect errors stop the session. Complete
source observations are a separate optional profile, not required by this path.

Every evaluation derives answers from its input snapshot. Dispatchable and similar
IDB relations are never manually called or retained as permanent facts. A later
snapshot may remove both input and derived tuples; no timestamp is needed on every
relation. Historical constraints need retained evidence or faithful summaries.

Backend-observed FSM mode confirms the actual post-state. Runtime-maintained mode
updates its protocol state after a confirmed effect. Neither mode discovers
unobserved external changes. Application-derived invariants can be required to
remain empty before and after effects.

A business refusal, a policy refusal and an execution error are different outcomes.
Uncertain effects stop the session, with no retry/reconciliation subsystem in this
prototype. Durable operations and cross-worker coordination are deployment-owned.

## Integration review

For each original requirement, identify its rules, input producers, actual effect
boundary and test evidence. Record partial coverage explicitly. In particular,
check both single-object and bulk release, every message/context/export path, and
whether an underlying backend retains stricter checks than the policy program.

Translation distills original NL into reviewed requirements before translating
rule targets. Adapter obligations and unsupported requirements remain visible.
Model output cannot register authorities, redefine a foundation or grant itself
an exception to a denial. A bundle hash pins content; it is not semantic proof.

The [Python API](../runtime/python/README.md) is the implementation reference.
Grokbot is one optional host. The private worker transport is not a public MCP
service; an MCP handler uses the same guarded business-call boundary.
