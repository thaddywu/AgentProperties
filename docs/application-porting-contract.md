# Application porting: policies, mechanisms, execution and observations

Design contract, 2026-11-03. This document defines the target application boundary. It does not introduce a new manifest parser or change the version-1 `runtime.json` format. The generic action SDK and Nova profile implement parts of the boundary; the status table below identifies the remaining work.

The framework accepts an application's policies and mediates observable operations. Grokbot is one host adapter. An application's backend, agent library, model provider and UI are outside the policy runtime. Resource FSM transitions are a supported mechanism in the target design, alongside optional IFC and capability modules; their execution integration remains to be implemented.

## 1. Four inputs, with explicit ownership

| Input | What it specifies | Author and authority |
| --- | --- | --- |
| Application policy | Natural-language requirements, or reviewed Datalog rules; application relations, constraints and goals | Application author. A model may translate or propose rules within the enabled contract. |
| Mechanism configuration | Enabled IFC/capability/FSM modules; app-defined grants, label groups, resource types, states and transitions | Application author and trusted configuration authority. A model may propose changes; installation validates them. |
| Execution protocol | Logical stores, fact/rule placement, permitted transfers, evaluation phases, decision hooks and commit/recovery mode | Integration developer selects a supported profile. Application authors may request a plan; validation must check it against actual hooks, authority and deployment constraints. |
| Observation binding | Which real events or authoritative snapshots produce each EDB relation, argument mappings, source authority, scope, freshness and completeness | Trusted framework/application adapter. A declaration must resolve to implemented instrumentation; policy text cannot create a fact source. |

Students can write policies and business FSMs without implementing a new backend. A developer must still connect each distinct backend's identity, observation and effect hooks. Someone who owns both the application and its integration may author all four inputs, but their roles remain separate. Installed policies cannot modify the adapter's authority or grant agent-side fact assertion privileges.

The existing application-description format remains `app.md`, numbered `policy.md`, `tools.md` and `agents/*.md`, including actual system prompts or scripted decision logic. Episodes remain optional. An advanced author can supply reviewed Datalog instead of invoking translation; both paths must target the same installed contract and pass the same validation. A direct-Datalog loading CLI for arbitrary student packages is not yet provided. FSM and deployment notation below are design examples, not additional course submission requirements.

## 2. Connect a backend other than Grokbot

```text
Student backend / agent framework
  └─ trusted adapter
       ├─ identity + authoritative observations
       ├─ mediated send / receive / read / tool / resource action
       └─ effect transaction + successful-event receipt
              ↕
       provider-neutral policy runtime
         local EDB → closure → decision → controlled effect/commit
```

There are two deployment choices:

1. **In-process:** the adapter calls the existing TypeScript SDK and supplies the real operation as a callback. The independent Document Vault and approval pilot demonstrate this boundary without Grokbot.
2. **Service/gateway:** a non-TypeScript backend uses the same logical boundary over authenticated RPC/HTTP. This transport is a target adapter, not an endpoint implemented today. A trusted gateway can execute registered operations, or the backend adapter can hold a transaction/lock while the service evaluates the bound snapshot and consume a single attempt result at commit. The adapter contract must specify which arrangement it supports.

A remote integration must not serialize a JavaScript callback, return an unrestricted boolean authorization token, or implement a check-now/execute-later sequence over changing state. Principal, operation, resource, snapshot version and attempt identity stay bound through execution; source refresh, replay handling and uncertain outcomes are adapter responsibilities. An RPC connection alone supplies none of these guarantees.

The agent-facing surface expresses intent. The trusted surface obtains authenticated identity, selects the operation and store, supplies observations and executes the effect. A model cannot select arbitrary source callbacks, impersonate a principal, install a protocol, or write runtime-owned facts. Query/proof access also requires authorization because metadata and explanations can disclose protected information.

Complete mediation is a deployment condition: received payloads must be checked before entering an inbox/model context, and relevant reads/tool results must be observed before their information is used. An SDK cannot protect operations that bypass its trusted adapter or isolate malicious host code sharing its memory.

## 3. What builtin means

Builtin consists of validated rule foundations **and** the runtime mechanisms that make their inputs and decisions meaningful. A predefined predicate name alone is not a guarantee.

| Component | Runtime supplies | Application supplies |
| --- | --- | --- |
| Kernel | Validated schemas/rules, bounded stratified closure, selected gate semantics, isolated state scope, attempt lifecycle, versioned inspection and effect/observation ordering | Protected operations, resource/principal identities and adapter implementation |
| Capability module | Interpretation of verified grants/requirements and composition with the action gate | Capabilities, grants, requirements, issuer and revocation/freshness policy |
| IFC module | Trusted source/import bridges, configured dependency tracking and label propagation, successful-receipt knowledge and receive-before-release ordering | Source classification, group membership, disclosure constraints and authorized ingestion/transport adapter |
| FSM module | Current-state validation, deterministic transition checks, authorization composition, serialized state replacement, success-only history and recovery requirements | Resource types, states, initial state, transition table, guards and real operation binding |
| Query/provenance | Inspection and hypothetical reasoning over the installed policy and a named snapshot | Query permissions, observer scope and application goals |

Mechanisms are enabled by the application profile. An application that needs an FSM can use the builtin mechanism without taking Nova's audit rules or IFC configuration. Application-specific relations such as `Auditor`, `AuditGoal`, an exposure threshold and a Board exception remain outside the kernel. Model-generated rules cannot replace a selected mechanism's immutable invariants.

Time-based expiration, scheduling, semantic classification/redaction and cryptographic integrity require actual trusted mechanisms or adapters. They are not implemented by inventing `Expired`, `Sanitized` or `Verified` relations. A requirement with a missing producer or hook is unsupported at installation.

## 4. FSM is an execution mechanism

Use the existing shared vocabulary:

```text
ResourceType(Resource, Type)                    trusted resource registry
ResourceState(Resource, State)                  runtime-maintained current state
Transition(Type, Action, From, To)               trusted machine configuration
ActionTaken(Event, Resource, Action, From, To)   committed execution observation
EnabledAction(Resource, From, Action)           structural candidate, derived
ReachableState(Resource, From, To)              graph reachability, derived
```

For example, an application defines `draft --approve--> approved --publish--> published`. A policy adds who may approve or publish, separation of duties and any information-flow constraints. A transition edge grants no permission by itself. `EnabledAction` retains its existing state-indexed meaning; the gate must join it with the actual `ResourceState`. `ReachableState` remains structural and does not prove a policy-compliant executable path.

The protected transition has this contract:

1. Resolve the resource's authoritative type/current state and acquire the configured serialization/transaction boundary. Use the latest admissible fact/configuration snapshot at that boundary.
2. Find exactly one transition for `(type, action, current state)`. Unknown resources, missing/ambiguous transitions or invalid state fail before the effect. Concurrent attempts on one resource cannot both authorize against its old state.
3. Add the runtime-owned temporary request. Compute the local stratified closure using the policy and selected foundations. Apply the profile's explicit authorization rule and all applicable denials/guards.
4. Invoke the registered operation only if both the transition and authorization pass.
5. On confirmed success, replace the one current-state tuple and append an immutable `ActionTaken` plus actual successful observations. The effect, state and observations share the adapter's documented commit boundary; do not append a second current state.
6. A denied or confirmed no-effect failure produces no successful transition. A failure with uncertain external effects enters recovery and blocks incompatible new actions until reconciled. It must not be represented as a successful action or automatically retried as if nothing happened.

Machine definitions and initial resource registrations are trusted configuration. Ordinary agents request operations; they cannot assert `ResourceState`, `ActionTaken`, grants or a successful approval. Per-resource single-process serialization is an initial implementation scope; cross-worker exclusivity requires an external authoritative transaction/coordination implementation.

Today, `runtime/src/lifecycle.ts` validates supplied type/state uniqueness and deterministic transitions and derives graph relations. It does **not** execute the sequence above. `createPolicySession.execute` already offers serialized authorization/callback/success-observation commit within one session, but only supports additive observations and has no integrated FSM state replacement. Connecting these two mechanisms is the next execution slice, not an already completed feature.

## 5. Specify rules and execution semantics separately

Rules describe inference and policy decisions. The execution protocol declares where that inference is meaningful and which effect consumes its outputs. The following is illustrative, not accepted syntax:

```yaml
profile:
  mechanisms: [capability, fsm]
  gate: explicit_allow_deny_overrides

rules:
  source: application_policy_datalog
  writable_heads: [Allow, Deny, ReadyToPublish]

stores:
  resource_authority:
    owns: [ResourceType, ResourceState, ActionTaken]
    imports: [Role, Approval]

evaluation:
  action_guard:
    at: resource_authority
    before: operation_effect
    rules: [selected_foundations, application_policy_datalog]
    outputs: [Allow, Deny]
  completion:
    at: authorized_observer
    after: confirmed_commit
    outputs: [ApplicationFinished]

effects:
  publish:
    adapter_operation: document_store.publish
    commit_mode: adapter_transaction
```

The author can request a profile/placement; the integration validates that `document_store.publish`, its transaction and the observation bindings actually exist. There is no arbitrary executable code, SQL, network route or filesystem path in model-generated deployment output.

Initially, a single authoritative gate is a reasonable default for resource/tool workflows. Logical principal stores can coexist within one process. Distributed local enforcement is a separate supported profile with explicit export/import channels and completeness/version rules; it is not selected automatically from the first tuple argument. Global observer results are authorized inspection inputs and cannot silently feed a local gate.

### Closure schedule

- Installing a bundle validates rule safety/stratification, schema, writers, input producers, placements, body locality, enabled mechanisms, decision roles and acceptance cases.
- Before an effect, the gate obtains a coherent committed snapshot, stages only declared attempt inputs and computes the local fixed point stratum by stratum. Required unavailable/stale/incomplete evidence blocks the attempt before absence is interpreted through negation or a deny-based gate.
- A confirmed successful commit changes EDB/state. Relevant local derived facts are recomputed or invalidated; observers evaluate only their declared rules over authorized inputs after the corresponding version is available.
- Query/Why/What-if select an installed policy and snapshot. Hypothetical inputs do not commit. Derived caches must be keyed by policy/configuration/input versions and cannot authorize a later operation without rechecking its actual commit-boundary snapshot.

The generic action profile currently requires explicit `Allow` and no `Deny`. Nova's receive profile currently allows a valid receive after complete evaluation when no `DenyReceive` exists. Both must be declared explicitly; naming a predicate does not switch between them.

### One application across the four inputs

For a document service, the author declares the machine `draft --approve--> approved --publish--> published` and the policy that a reviewer cannot approve their own document; publication requires the publisher role. The admitted application rules can be written directly or generated from that policy:

```prolog
Allow(Q) :- Request(Q, A, "approve", D),
            Role(A, "reviewer"), Author(D, Owner), A != Owner.
Allow(Q) :- Request(Q, A, "publish", D), Role(A, "publisher").
```

The FSM module checks the current state and transition in addition to these rules; `Allow` alone cannot publish a draft. The source binding supplies `Role` from an authoritative account snapshot and `Author` from the document registry. The runtime owns `Request`, `ResourceState` and successful `ActionTaken`. The execution profile runs the closure at the document authority before invoking its registered `approve`/`publish` operation, and commits the state/history under the declared transaction.

If another policy needs the identity of a past reviewer, declare an actual successful-approval observation such as `Approval(Document, Reviewer)` with a producer that binds the authenticated actor at commit. The existing five-argument `ActionTaken` does not itself contain an actor, timestamp or approval validity period. Event metadata or explicitly bound app relations must supply those fields; translation cannot infer them from the current caller or action name.

## 6. Declare how the runtime obtains EDB

Each input relation needs both a schema and an implemented producer. For example:

| EDB | Producer | Materialization and validity |
| --- | --- | --- |
| `Role(Actor, Role)` | Authenticated account/role service adapter | Authoritative snapshot for declared actors/scope; refresh before a sensitive decision or use a declared valid version |
| `Approval(Document, Reviewer)` | Approval service transaction | Confirmed successful approval event or complete current snapshot; define whether later revocation changes its meaning |
| `ResourceState(Resource, State)` | State authority plus FSM commit hook | Exactly one committed value; replaced only through registration/recovery or a successful protected transition |
| `Received(Principal, Message)` | Successful receive hook | Created after actual accepted delivery under the protocol's commit boundary |
| `TransportTag(Message, Tag)` | Verified transport import | Bound to origin, message/payload, recipient and policy/protocol context; attempt-scoped until successful delivery |
| `ClaimedApproval(Agent, Document)` | Agent statement | Explicitly unverified claim; never interchangeable with `Approval` |

An illustrative binding entry could say:

```yaml
predicate: Approval
kind: input
arguments: [Document, Reviewer]
producer: approval_service.current_approvals
authority: approval_service
store: resource_authority
mode: authoritative_snapshot
scope: requested_document
refresh: before_action_guard
completeness: all_current_approvals_for_requested_document
```

`producer` names an adapter-registered function. That function maps real authenticated application data into facts, with argument validation and source/version metadata. The declaration neither implements the function nor proves its observations true. Initial implementation should use small explicit mapping functions and shared offline conformance cases, not a model-authored general instrumentation language.

Distinguish four observation classes: trusted configuration, authoritative snapshots, committed runtime events and authenticated protocol imports. Keep unverified agent claims separate. Replace stale snapshot facts within their declared scope, including deletions/revocations; retain event history according to its historical semantics. A message's prose is not a source of permissions or successful events.

Negation requires a complete authoritative scope. `not Approval(D, A)` is meaningful only when the gate has all relevant current approvals under the declared snapshot contract. Fetch failure, an unobserved event or a foreign store's local absence is unknown evidence, not a proven negative. A rule reading another principal's local input requires a declared permitted transfer/query materialization and suitable completeness guarantees, including through helpers and recursion. Otherwise installation rejects it as unsupported.

## 7. Concrete porting sequence

1. Collect the existing application Markdown and identify protected operations/resources and application policies. Mark unresolved semantics explicitly.
2. Select the kernel gate profile and required builtin modules. Write the application FSM/guards if needed; keep resource progression distinct from message delivery lifecycle and accumulated IFC labels.
3. Inventory EDB needed by the rules and map every input to an implemented trusted source. Add missing hooks explicitly rather than asking translation to invent facts.
4. Select a supported store/evaluation/commit profile. Declare authorized imports and observer queries; reject unavailable locality/freshness/transaction requirements.
5. Translate NL policies or load reviewed direct Datalog over this exact contract. The model may add admitted helper IDBs; input creation and mechanism invariants remain protected. The current Nova extension compiler does not yet admit arbitrary helpers.
6. Produce a versioned bundle linking rules, selected mechanisms, schema, protocol and source binding. Validate at installation and replay/restore. This richer artifact is a target beyond the version-1 generic bundle.
7. Run backend-neutral conformance cases: invalid identity/facts, missing inputs, forbidden/allowed actions, transition ordering, concurrent attempts, callback failure/recovery and denied-payload isolation where applicable. Then evaluate task completion independently.

## 8. Implementation boundary

| Capability | Current evidence | Work remaining |
| --- | --- | --- |
| Backend-independent local action gate | Existing SDK, Document Vault and independent approval pilot | Distributable adapter examples and non-TypeScript service transport |
| Schemas and safe policy inference | Input/derived and arity checks, bounded stratified evaluation | Rich runtime types, producer/authority and complete placement validation |
| IFC/capability foundations | Fixed shared rules and executable Nova hooks | Generic messaging adapter, authoritative-source completeness and remote transport security |
| FSM definitions and graph analysis | Lifecycle validator and enabled/reachable relations | Transition + authorization + real effect + state/history commit, with appropriate recovery |
| Stores and closure schedule | Generic session-local queue; Nova principal-local stores and observer | Unified validated execution profile and source/version binding |
| EDB materialization | Trusted facts passed by adapter; Nova hardcoded event producers | Explicit producer registry and authoritative snapshot/update contract |
| External effect recovery | Responsibility documented and failure boundary demonstrated | Adapter transaction/idempotency/reconciliation implementations per backend |

This is the system boundary to freeze before expanding the student corpus or claiming broad expressiveness. RQ1 can then separate rule expressibility from missing observations/mechanisms; RQ2 can evaluate translation within a fixed contract; RQ3 can test actual mediated effects and legal task completion.

[Runtime API](../runtime/README.md) · [Nova-specific inventory](nova-runtime-contract.md) · [Pilot evidence](nova-evaluation-pilot.md) · [Manuscript submodule](research/)
