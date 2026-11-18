# Observations, EDB and policy translation

This design describes the boundary between application evidence and policy rules.
It is intended to be read with the [staged port workflow](port-pipeline.md) and the
[executable port contract](../../src/policyweave/policy_adder/porting-contract.md).
Examples use synthetic application objects. They do not report an application
evaluation or establish complete mediation.

## Evidence before conclusions

The extensional database (EDB) contains supplied input facts. Datalog derives
relationships and authorization conclusions from those inputs. The host executes
the original business operation only after the gate permits it. A successful
translation must therefore establish all three links:

1. An actual producer supplies each input, with a documented meaning and lifetime.
2. Rules express the policy condition over those inputs.
3. A gate consumes the conclusion before the relevant effect or disclosure.

A rule without a producer cannot check the real application. A helper conclusion
without a consuming gate cannot prevent an effect. A gate decision does not prove
that the operation subsequently succeeded. Compilation validates a declared
contract; it does not discover missing producers or prove that the contract
describes the application correctly.

Foundation rules for capabilities, provenance and state transitions are shared.
PrincipalGroup records direct role/user-group membership; InGroup computes its
nested closure without granting permission by membership alone. The optional `observations` mechanism
adds input schemas, with no authorization rules. Applications still supply the
domain conditions and the real observation integrations.

## Shared observation schemas

Select `mechanisms=("observations",)` when constructing `Policy`; selected
mechanisms supply their own declarations. Do not redeclare them in application
rules. The schemas are defined in the shared
[catalog](../../src/policyweave/core/foundations.json).

| Relation | Meaning and storage semantics | Producer obligation |
| --- | --- | --- |
| `Field(Object, Name, Value)` | A host-observed field or association; symbol or binding-validated int64 values and set semantics. Several values can coexist for one object/name. | Define each field name, value encoding, allowed cardinality, scope, source and removal/replacement behavior in the binding. |
| `Event(Id, Principal, Kind)` | Retained event identity with key `Id`; append-only. A different row cannot replace the same ID and the relation cannot be deleted through the EDB API. | Observe an actual occurrence, bind its actor and kind, and separately record the fields needed to interpret it. |

Both relations are `hostOnly`. They cannot be exposed as FactTool write
targets. That restriction protects the write interface; it does not authenticate
the underlying source or make an incorrect host adapter truthful.

`Field` is deliberately set-valued. Recording `Field("job-1", "owner", "agent-a")`
does not automatically replace an old owner. If the binding promises one current
owner, its producer must remove the obsolete row and insert the new row in the
same trusted update. History and current state need distinct names or subjects.
The generic schema alone does not enforce cardinality per field name; the optional
observation contract below can reject conflicting values for declared single
fields. It does not turn insertion into automatic replacement.

Numeric fields declare a fixed unit in their definition. Missing, stale,
out-of-range or unparseable values are not zero or permission. Conversions and
rounding require reviewed, policy-independent producers. Current-value changes
use explicit field removal/insertion or refreshed backend snapshots; no separate
measurement relation supplies implicit replacement.

`Event` carries neither parameters nor outcome. The producer may record observed
parameters, outcome and time/order as `Field` rows, under
the binding's declared names. Append-only event identity does not make related
`Field` rows immutable, ordered or complete. Retention, corrections,
unique IDs and restart behavior remain explicit integration obligations.

## Frozen observation and call contracts

The port binding also freezes reviewed static configuration before rules. Roles
and user groups use the existing `PrincipalGroup` input; shared `InGroup` supplies
nested membership. For example:

```prolog
PrincipalGroup("learner", "doctoral").
PrincipalGroup("doctoral", "students").
```

`InGroup("learner", "students")` follows from those facts without a new
`Student(Principal)` relation. Membership does not grant an operation by itself.
Capability facts configure grants; policy conditions still govern the final gate.
The plan's `configuration` entries name a selected static input, string arguments,
meaning and exact original-policy/application evidence. Rules must preserve
exactly those configured facts. Runtime memberships require an actual trusted
identity producer. A principal supplied by an agent is not authentication.

`Policy` accepts optional `observation_contract` and `call_contract` arguments;
their binding artifact names are `observationContract` and `callContract`.
Existing integrations can omit them. The staged fixed-EDB port harness always
generates them from its accepted binding plan and installs them through a
host-generated `policy_port.binding.make_policy` factory.

An observation contract contains `fields`, mapping each field name to a
definition with `cardinality` (`one`/`many`), `type` (`symbol`/`number`), fixed
`unit` (a string for numeric fields or null), and `observedAt` (a timestamp-field
name or null). The runtime rejects unknown names, malformed int64 numbers and
conflicting `one` values. `observedAt` must reference a single numeric `unix_ms`
field; a measured field requires that timestamp on the same object in the final
snapshot. The metadata does not supply an observation, convert units or enforce
freshness. Rules must check the actual time against their policy condition.
`one` means at most one value, not mandatory presence or automatic replacement.

A call contract maps each action to its permitted parameter names and types:
`symbol`, `number`, `boolean` or `json`. The gate rejects unknown actions and
supplied parameter names outside that action's registry; typed values must have
the required encoding, including canonical int64 numbers and `true`/`false`
booleans. This is a vocabulary/type boundary, not an assertion that every declared
parameter is present. Function binding, adapters and rules must preserve required
argument and missing-value behavior. Nested dictionary leaf paths follow the
runtime's underscore-joined parameter encoding.

The source-backed plan validator checks actual Python function/method symbols
and their signature names, exact unique evidence quotations, parameter-path shapes
and types, field/metric registries, planned derived signatures and dispositions
for original P-numbered policy sections. It recognizes simple dispatcher action
branches as an additional completeness check. These checks establish concrete
source references and internal consistency; they do not automatically prove all
per-action field mappings, producer meanings or exhaustive path coverage.

## Requests, events and results

`Request(Q, Principal, EventKind)` and `Parameter(Q, Name, Value)` describe the
current gated invocation, bound to actual call arguments. They are not a retained
history of successful operations. A host-observed event for that same invocation
may reuse `Q` as its `Event` ID. The runtime does not automatically turn a request
into an event or turn an allowed call into a successful event.

For example, after observing a synthetic payment receipt, a producer could record
`Event("call-1", "agent-a", "send_payment")` together with
`Field("call-1", "outcome", "applied")` and an observed receipt ID. The mere
existence of that `Event` would still not prove success: rules requiring success
must check the explicit outcome and any required receipt binding. A rejected
attempt, a confirmed effect and an uncertain network response must not share an
undocumented interpretation of the same field.

Before-call observations, such as actual account balance or current server time,
must be available in the captured gate inputs before evaluating a request that
needs them; a managed before-hook can stage them without publishing the batch.
Result observations belong after the application's real success criterion.
Post-success facts can authorize a later operation, never retroactively authorize
the operation that produced them. Preserve `NotApplied` only when the trusted
backend can certify the absence or rollback of every relevant effect; preserve
`Unknown` when it cannot. A returned Python value alone is not a universal success
criterion. See the [effect contracts](../../src/policyweave/core/contracts.py) and
[runtime guide](../../src/policyweave/enforcement/README.md).

## Observation is not policy evaluation

Adapters may read actual arguments, parse numbers, normalize identifiers, convert
units, read stored fields and compute policy-independent quantities. Datalog owns
policy thresholds, ownership joins, grants, approval validity, lifecycle conditions
and allowance/refusal. Keeping existing application guards is permitted, but a
port must identify them as delegated checks rather than attribute them to rules.

An arbitrary field name is still a schema contract. A Python function that writes
`Field(job, "Eligible", "true")` after checking policy thresholds has hidden the
policy in the adapter. Renaming it `assessment` does not fix
that split. Supply the underlying values and express the comparison in Datalog.
An existing application record with such a field may be observed, but its origin
and any delegated decision must be disclosed; observing it does not implement the
policy condition in the generated rules.

For a synthetic scheduler, adapters can supply requested memory in bytes, current
usage in bytes, recorded owner and the requesting agent. Rules can join the job
ID with the owner and compare the quantities with the configured limit. If the
real scheduler never reports usage, a field name cannot fill that gap. Report the
missing producer and the affected requirement.

## Write authorities

| Interface | Authority and use | What a successful write establishes |
| --- | --- | --- |
| `Policy.put/delete/update` | Trusted host ingestion, including real observations and confirmations. Writes inside a guarded synchronous operation join its staged batch. | The host accepted an input update under its contract; source authenticity remains the host's responsibility. |
| `FactTool.put/delete` | An agent connection bound by the host to a principal and an explicit allowlist of mutable input predicates. Every action is authorized against pre-write facts. | A policy-authorized decision or other permitted fact was recorded. Recording does not execute the business operation. |

`caller_context` carries the application's reported caller name. It is not
authentication. MCP metadata and agent-chosen arguments cannot substitute for a
trusted identity boundary. State whether each integration has authenticated
identity or only reported identity.

FactTool cannot assert derived rows, request facts, reviewed configuration or
host-only observations. Policy must constrain the selected predicate, issuer,
target and values. The pending row cannot authorize itself. `put` is idempotent
for an identical row and rejects a different row with the same key; `delete`
requires the complete current row. Put and delete need separate permissions.
There is no agent-facing atomic replacement across two calls. Host `Policy.put`
retains its keyed replacement semantics.

When the source policy gives an agent decision authority, its FactTool decision
can be authoritative for that purpose. For example, an authorized synthetic
payment reviewer may approve an operation it actually received, with the operation
ID and exact contents/version bound by the application. No additional oracle is
needed to prove that the authorized reviewer decided. However, the tool cannot
invent the review delivery, human confirmation or operation lifecycle. Missing
infrastructure remains a gap; adding a new confirmation workflow changes the app.

There is no dedicated agent self-statement mechanism. Existing messages can
retain claims without turning them into verified observations. `Source` and
`DependsOn` describe actual or conservative possible origins/dependencies, not
proof of content truth. A generic FactTool can expose non-host-only inputs only
with an explicit allowlist and per-write policy authorization; the availability
of that API is not evidence that an application has trusted dependency capture.

## Translation against a fixed binding

The rules-only `translate(source, binding, generate)` API starts with a trusted,
existing binding. It decomposes exact source spans into requirements, classifies
implementation obligations, generates rules for Datalog targets, validates them
and independently reads those rules back. It pins hashes of the source, contract
and documents, and returns a draft that is not installed automatically.

The source policy states what should hold. The binding states what actual inputs
and gates mean. Implementation evidence supports the binding. For every proposed
requirement, keep these questions separate:

- **Datalog:** Can a read-only condition be expressed over available, correctly
  bound inputs? Missing prewritten domain rules alone is not a language limit.
- **Adapter:** Which actual producer, gate or result update is required? A declared
  predicate without its producer does not discharge this obligation.
- **Claim or decision:** Is an agent supplying an unverified assessment, or does
  policy grant that agent authority to decide this exact question? Bind the
  appropriate checked interface without turning claims into observations.
- **Unsupported or ambiguous:** Which required capability or interpretation is
  missing? Preserve the clause and explain the gap; do not weaken it to pass tests.

These are design distinctions, not a new translator enum. The current requirement
artifact uses `datalog`, `mechanism`, `adapter`, `unsupported` and `ambiguous`;
claim/decision authority must be described within the binding and obligations.

The executable port harness has a separate binding-plan schema. Its requirement
dispositions are `supported`, `partial`, `unsupported` and `ambiguous`, with exact
source quotes and affected call references. It requires `agent_writes` entries
for existing decision operations. Unlike the
general policy API, this fixed-EDB workflow forbids new domain input predicates:
use selected shared inputs and frozen observation names. Planned derived relations
retain their argument names/types. Custom IDB starts empty; at most eight helpers
may be planned with a purpose and justification for not inlining. Accepted uses
are negative existence projections, reused nontrivial joins, actual recursion
and registered global violations. Simple aliases, unused helpers and unplanned
predicate names are rejected. These checks do not prove mathematical minimality.
Helpers cannot introduce `.input`, redeclare stock relations or create new EDB.
All final IDB declarations freeze with the accepted rules hash; instrumentation
cannot add or change them. It cannot invent an `Approval` input
relation merely because the general FactTool API could mediate such a relation
in an application that already has the appropriate trusted binding.

Finite, function-free, stratified Datalog supports joins, negation and signed
integer comparisons. The gate requires explicit `Allow` and absence of `Deny`;
denial wins. Rules cannot perform a payment, obtain a confirmation or ensure that
an agent eventually takes an action. Bounded integer checks require actual typed
inputs with compatible units and scopes. Missing observations and future
obligations cannot be repaired by inventing an EDB seed.

Versions, approvals, ownership and receipts can be represented by Field links
and direct joins; they do not require domain-specific predicates. A complex
negative existential can justify a projection. For example, if `Allocation(Job, Node)` is a derived join over frozen
observations, `HasAllocation(J) :- Allocation(J, N).` projects whether any matching
allocation exists. A later clause with a positively bound job can use
`not HasAllocation(J)`. This is clearer than inserting diagonal support tuples
into an unrelated compatibility or allocation relation to encode existence.
The projection introduces no new observations or authority. Independent reading
should explain its meaning with the gate and policy condition that consume it,
rather than treat each helper as a separate permission.

## Implementation status and limits

Implemented primitives include the shared observation schemas, optional frozen
observation/call contracts, synchronous `Policy` annotation, host fact updates,
checked FactTool writes and rule translation.
Their implementation owners are
[core policy](../../src/policyweave/core/policy.py),
[EDB updates](../../src/policyweave/enforcement/edb.py),
[FactTool](../../src/policyweave/enforcement/fact_tools.py),
and the
[translator](../../src/policyweave/policy_adder/pipeline.py).

The executable adapter now uses a host-owned
[harness](../../src/policyweave/policy_adder/harness.py) and
[binding validator](../../src/policyweave/policy_adder/binding.py): read-only
discovery and planning, a hashed binding freeze, rules-only editing and subsequent
instrumentation with structural/native trace checks. The
[port workflow](port-pipeline.md) describes these four enforced stages and the
seven responsibilities they cover. Independent back-translation and alignment
remain later entries; `CodexPort.translate` does not run them automatically.

Source citations, frozen vocabulary and development traces do not prove producer
semantics, exhaustive mediation or policy fidelity. Static Python checks are not
a proof against malicious helper code. Full mediation, authenticated identity,
distributed consistency and outcome reconciliation require separate application
evidence. This document reports no newly completed application run.
