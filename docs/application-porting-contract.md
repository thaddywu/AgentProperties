# Application porting: policies, mechanisms, execution and observations

Design contract, 2026-11-03. This document defines the target application boundary. It does not introduce a new manifest parser or change the version-1 `runtime.json` format. The TypeScript action/FSM SDK and backend-neutral messaging port implement the interfaces described below; the status table identifies the deployment limits.

The framework accepts an application's policies and mediates observable operations. Grokbot is one host adapter. An application's backend, agent library, model provider and UI are outside the policy runtime. Resource FSM execution, IFC propagation and capability checks are implemented in the shared runtime. The backend supplies identity, trusted observations and real effects.

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
Application → its backend (or in-app orchestration)
  └─ trusted adapter / port
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
CanTransition(Resource, Action, From, To)        current-state candidate, derived
ResourceRecovery(Resource, Attempt)             runtime-owned uncertain outcome
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

`RuntimeBinding.mechanisms: ["fsm"]` now enables this execution sequence in `createPolicySession`. The binding must declare the schemas from `LIFECYCLE_PREDICATES`. Installation appends immutable foundation/gate rules, and validates unique types/current states and deterministic transitions. A session serializes operations, replaces current state and records success only after the callback resolves. `EffectNotAppliedError` certifies no effect; other failures enter `ResourceRecovery`. Trusted `reconcile(attemptId, "applied" | "not_applied")` resolves an attempt without repeating its callback. Ordinary input updates cannot rewrite machine definitions, state or history. Recovery bookkeeping and queues are process-local; restart recovery and multi-worker exclusivity need backend-owned durable attempts and transactions.

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

## 8. Implemented interfaces and primitive vocabulary

The supported installation API is TypeScript, rather than the illustrative YAML above:

```ts
import { createBackendPort } from "@rakazo/policy-runtime/backend-port";
import { novaMessagingProfile } from "../apps/nova/src/ports.js";

// A saved translated artifact or the reviewed reference rules; identical core.
const profile = novaMessagingProfile(validatedArtifact);
const port = createBackendPort({
  profile,
  observations: [{
    id: "grants", scope: "application", predicates: ["AgentHasCapability"],
    read: async () => ({ version: "snapshot-2", complete: true, facts: currentGrants }),
  }],
  deliver: async message => inbox.commit(message),
});
// The trusted backend binds this from its authenticated run context.
const agent = port.bind(authenticatedPrincipal);
await agent.send(recipient, stableAttemptId, body);
agent.query('?- Knows(A,T).');
```

A different backend supplies the same `deliver` and observation contracts. `createMessagingProfile` constructs a new app profile without importing Nova: principals, source authorities, configuration, application relation schemas/rules, and their local/replicated/observer placement. For a new application, use its own schemas, config and source rather than importing Nova:

```ts
import { createMessagingProfile } from "@rakazo/policy-runtime/messaging";
import { parsePolicyRules } from "@rakazo/policy-runtime/query";

const profile = createMessagingProfile({
  principals, sourceAuthorities, configuration,
  application: {
    predicates: applicationSchemas,
    rules: parsePolicyRules(reviewedOrTranslatedDatalog),
    ruleEncoding: "parsed",
    local: applicationLocalPlacement,
    replicated: shareableApplicationInputs,
    observer: observerHeads,
  },
});
```

`parsePolicyRules` rejects ground fact injection and embedded queries. Profile/runtime installation checks the parsed rules against the declared schema, foundation and locality. Translation must target this exact admitted vocabulary; the Nova translator's fixed schema does not automatically translate arbitrary student apps. The generic action translator already targets an app-owned `runtime.json`; arbitrary messaging-app translation still needs its matching prompt/bundle integration.

Application rules cannot replace foundation heads (except adding denials), schemas or primitive placements. `MessagingRuntime` is the trusted execution implementation; hand agents only the bound port. Profiles, snapshot restoration, observation functions and administrator inspection are trusted surfaces, not model tools.

| Primitive | Kind / arguments | Implemented meaning and writer |
| --- | --- | --- |
| `MessageSender(A,M)` | EDB | Runtime send hook binds actual sender. |
| `MessageReceived(A,M)` | EDB | Port commits only after confirmed accepted delivery. |
| `ReceiveAttempt(A,M)` | Temporary EDB | Runtime stages before the receiver's gate; removes on resolution. |
| `ReceivedBeforeSend(Min,Mout)` | EDB | Runtime records previously received messages when output is created. |
| `SourceTag(M,T)` | EDB | Trusted `ingest`, restricted to declared source authorities. |
| `ImportedTag(M,T)` | EDB | Engine imports the sender's derived envelope; retains only on successful receipt. |
| `AgentHasCapability(A,C)` | EDB | Trusted app configuration or complete authoritative grant snapshot. |
| `TagRequiresCapability(T,C)` | EDB | Trusted policy configuration. |
| `TagGroup(T,G)` | EDB | App's label/group configuration. |
| `MessageDependsOn(Mout,Min)` | IDB | Same sender's prior receipt plus receive-before-send relation. Conservative dependency, independent of message prose. |
| `MessageCarries(M,T)` | IDB | Source/import bridge plus recursive dependency propagation. |
| `Knows(A,T)` | IDB | Successfully received tracked label. It does not infer all semantic knowledge of an agent. |
| `DenyReceive(A,M)` | IDB | Foundation capability check plus application denials. Absence of a denial permits a well-formed attempt after successful complete evaluation. |

FSM schemas above are also exported through `primitives`. Legacy Nova UI/checkpoints and saved translation artifacts retain `Sender`, `Received`, `Incoming`, `TrustedSource`, `TransportTag`, `HasCap`, `Requires`, `MayDependOn`, `MessageTag`, `HasReceivedTag`. `PRIMITIVE_NAMES` maps these to the public names; both profiles use the same six-rule foundation. The canonical Nova port adds its app rules over that foundation. The old saved artifact hash is not silently redefined.

### Evaluation, EDB and effect schedule

1. Construct a profile and validate schemas, rule safety/stratification and locality. Register real snapshot producers and the delivery callback. Unsupported foreign-local dependencies/negation are rejected; no implicit remote query is invented.
2. Before each send, read every declared snapshot producer. Each must return a nonempty version and `complete: true`; failure blocks the operation. Replace its declared relations, including removals/revocations. Producers cannot write message/runtime event relations. Producer scope/version/completeness are trusted assertions by the binding code, not cryptographic proofs or automatically coordinated multi-source snapshots.
3. Serialize refresh, send staging, sender closure/envelope export, receiver closure and actual delivery callback. An unsuccessful evaluation or denied gate releases no payload to the callback. The sender conservatively records its attempted output; denied imported facts never become successful knowledge.
4. On confirmed callback success, commit receiver receipt and retained imports. Exact replay returns the prior outcome without repeating delivery. A callback certifying no effect leaves the attempt pending for refresh/recheck. An uncertain callback freezes dispatch until trusted `reconcile(messageId, "delivered" | "not_delivered")`.
5. Recompute local closure for queries. The observer closes only observer heads over the union of local closures; it does not rerun local denials globally. Agent queries exclude temporary imports and cannot inject rules/facts. Query visibility still needs the app's authorization policy.

The runtime queue is one process-local session. No automatic cross-worker lock, durable message/attempt storage, distributed atomic commit, authenticated remote transport or complete read/tool instrumentation is supplied. Backends must make authoritative reads and external effects valid under their own transaction/freshness contract. A plain callback does not make a database write and in-memory receipt crash-atomic.

### Bounded protocol selection

`synthesizeProtocol` accepts the installed program, reachable witness snapshots, declared shareable-input and rule-placement alternatives, optional local query observations, cost weights and an exact-search budget. It enumerates the finite space, preserves the full-copy program's closure and every observed local receive gate, and preserves declared queries against the original distributed profile. It returns a least-cost feasible plan with program/witness/search hashes and explicit scope. `applyProtocolPlan` binds the result to its program before installation.

The engine chooses storage/rule placement; the adapter supplies the fixed admissible source authorities and transport channels. Private grants cannot be made shareable by the search. Snapshot preservation is finite evidence, not a proof for all executions or asynchronous networks. Cost counts stored input tuples across snapshots, deployed rule copies and replicated tuple copies; it does not measure latency or bytes.

Nova's executable `port-demo-run.ts` loads either reviewed reference rules or an existing validated translated artifact, chooses a plan, executes delivery callbacks, and explicitly materializes authorized observer completion into an `AuditComplete` EDB for the report resource authority. Its report then follows `draft → approved → published` through actual FSM callbacks. That observation bridge is deliberate; global observer facts never appear in a local gate automatically.

### Where Grokbot needs the adapter

`grokbot/packages/adapters/src/message-policy-port.ts` implements a run-scoped adapter. `forRun(run)` binds the logical principal using verified `spaceId`, `userId`, `botId`; `send` derives an attempt ID from run ID and delivery key. Model arguments cannot choose the sender. Offline tests invoke the real shared port and show a forbidden report never reaches its delivery callback.

The production `messageBot` path in `grokbot/packages/adapters/src/bot-messages.ts` resolves/authorizes the recipient, locks both threads, deduplicates the delivery key and checks run validity before creating outbound/inbound blocks, task context and a recipient wake-up. For deployment, create one durable port/authority per policy scope at the composition root; bind the authenticated run after identity resolution; place the protected database commit inside the port's delivery boundary. The gate must precede **inbound block, model-context and wake-up creation**, and successful receipt must correspond to that transaction's confirmed commit. Keep notifications/enqueue after the commit, and bind policy attempts to existing idempotency keys. Do not acquire/release a gate lock separately from changing the state it authorized.

Instrument initial assignments, document reads, sandbox/tool results, memory/context imports and other relevant inputs as trusted ingestion before use. A send-only adapter cannot track information learned through unobserved tools. The existing native five-principal Grokbot policy path remains a compatibility path; the new adapter is available and tested but is not silently enabled for every production `messageBot` call. Persisting attempts and connecting all those sources are required before claiming full-host mediation.

## 9. Implementation boundary

| Capability | Current evidence | Work remaining |
| --- | --- | --- |
| Backend-independent action/FSM gate | Shared SDK, Document Vault, concurrent FSM execution and recovery tests | Durable sessions, external transactions and non-TypeScript service transport |
| IFC/capability messaging | Shared runtime used by Nova; same port tested with inbox/event-log sinks | Authenticated remote envelope transport and complete input mediation |
| Readable primitives | Canonical vocabulary plus explicit legacy aliases from one foundation | Rich entity types and additional implemented modules as policies require |
| Stores and closure | Generic principal-local stores and observer; remote-local rule rejection | General remote-query protocols and asynchronous correctness proof |
| EDB snapshots | Declared, versioned, complete producers; revocation before gating | Backend-specific freshness, coherent source transactions and authenticity |
| Protocol optimization | Exact bounded placement search, query/gate comparisons and deployed Nova plan | Channel synthesis, exhaustive/universal correctness, production cost measurements |
| External effects | Actual callbacks, replay protection, explicit uncertain-outcome reconciliation | Durable attempt recovery and crash-atomic commit per backend |
| Grokbot | Optional authenticated-run message adapter and offline callback tests | Production injection, durable scope management, all read/tool/context hooks |

RQ1 must separate rule expressibility from missing observations/mechanisms; RQ2 evaluates translation within this fixed contract; RQ3 tests actual mediated effects and legal task completion. These experiments establish a testable boundary, not a completed student-corpus study.

[Runtime API](../runtime/README.md) · [Nova-specific inventory](nova-runtime-contract.md) · [Pilot evidence](nova-evaluation-pilot.md) · [Manuscript submodule](research/)
