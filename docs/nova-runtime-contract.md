# Nova-centered runtime and translation contract

Status: contract proposal, 2026-10-28, with the first foundation extraction implemented. The six fixed IFC/capability rules and their schema now live in `runtime/src/messaging-policy.ts`; Nova's six app-specific reference rules remain in `apps/nova/src/policy.ts`. The UI exposes both layers. The golden executable rules, ordering and behavior are preserved. Nova extension artifacts can now be reviewed and installed into fresh sessions with the fixed protocol. General protocol synthesis and a connected resource state-machine gate remain proposed. Nova remains the primary example; Document Vault is a separate proof that a translated policy can control a local callback.

## Target boundary

```text
Framework or custom application
  → trusted adapter: identity, source/config authority, message/tool interception
  → our protocol runtime: local stores, event capture, label transport, gate and commit
  → framework inbox/model context/tool implementation, only after authorization

Application Markdown + enabled runtime contract
  → one-shot translation
  → policy Datalog + references to supported runtime mechanisms
  → placement/authority/schema/behavior validation
  → rules and protocol binding installed together
```

The runtime package must not know Grokbot, Board, audit budgets or a fixed set of principals. Grokbot supplies an adapter just as another framework would. An application implemented directly by its author can use the same wrapper APIs. Protected access paths must be mediated; an in-process SDK does not isolate malicious host code that directly reads memory or bypasses the wrapper.

Intercepting only a function named `send_message` is insufficient. Sender identity comes from the authenticated execution context; the target is resolved through the adapter's principal directory. At the receiver, the gate must run before enqueueing a readable payload, resuming an agent with it, or adding it to model history. Reads/tool results/source ingestion must also be observed if the system promises to track their information in later outputs. A send wrapper cannot recover dependencies on unobserved data.

The first extraction should preserve Nova's conservative dependency policy: every ordinary send depends on all earlier successful receives in that principal's runtime context. Source ingestion is a separate privileged operation. More precise per-computation tracking can follow after the framework can reliably observe all consumed inputs; it must not rely solely on an agent's claimed dependency list.

## Three ownership layers

| Layer | What belongs here | Who may change it |
| --- | --- | --- |
| Protocol kernel | Principal-bound contexts, message identity, pending/successful receive events, local-store isolation, designated decision hooks, delivery ordering and failure handling | Runtime implementation and trusted adapters |
| Bundled optional mechanisms | Conservative information-flow tracking, capability checking, resource lifecycle support | Versioned mechanisms selected by the application binding; model output cannot weaken their invariants |
| Application schema and policy | Domain roles, group membership, audit goals, exemptions, completion definitions and policy-specific helper relations | Trusted app configuration plus translated/validated rules, according to each relation's declared writer |

“Bundled optional” means ordinary reusable code and contracts initially, not a new plugin registry. A useful relation can be provided as a convention without becoming a mandatory kernel primitive. Having a built-in decision name does not mean its entire decision rule is fixed: the runtime owns what a denial does, while an admitted policy can derive the denial.

Every predicate contract needs arity and argument types, EDB/IDB kind, writer authority, placement, lifetime, any export/import mapping, and any execution-hook meaning. EDB/IDB is relative to a store: a local derived summary can cross an authorized export and become an input fact at another store. The runtime must retain its origin; it is not an unrestricted remote assertion.

## All current Nova predicates

The current Nova profile has 13 EDB and 6 IDB predicates. “Placement” below describes today's code; “proposed ownership” is the recommendation. Parentheses describe tuple order, not a new syntax.

| Predicate | Current kind, origin and placement | Proposed ownership and translation boundary |
| --- | --- | --- |
| `Sender(P, M)` | EDB captured by `send`, at sender P. The current event records a logical send/pending message, not proof of physical network delivery. | Kernel event. Bind P from context, not a caller-supplied identity. Model cannot assert it. |
| `Incoming(P, M)` | Temporary EDB at recipient P, before receive evaluation. | Kernel attempt state. Exists only for a validated pending delivery; model cannot assert it. |
| `Received(P, M)` | EDB written at recipient P only on successful delivery. | Kernel committed event. Becomes the canonical successful-receive observation. |
| `Receiver(P, M)` | EDB written with `Received` at the same successful-receive boundary; used by dependency rules. | Keep a compatibility alias during extraction; do not require adapters to independently assert two equivalent success events. |
| `Before(Min, Mout)` | EDB captured at the sender from earlier successful receives before this outgoing send. | Information-flow mechanism. This is local causal evidence, not a global ordering or a user-provided timestamp. |
| `TrustedSource(M, Tag)` | EDB from the privileged assignment path; currently Board-only. | Information-flow mechanism plus trusted ingestion authority. Remove Board as a kernel concept; applications identify legitimate source authorities. |
| `TransportTag(M, Tag)` | Protocol-imported EDB at recipient. Temporary until allow, retained after allow, removed on deny. | Information-flow mechanism. Import only from a valid envelope; a message's prose cannot mint labels or remove them. |
| `HasCap(P, Cap)` | Trusted config EDB local at P. | Optional capability mechanism. Grants/revocations come from an authority, never model inference or agent claims. Capability names and grant facts are app data. |
| `Requires(Tag, Cap)` | Replicated config EDB for tag-specific requirements. | Optional capability/IFC integration relation. A policy may propose a requirement through an explicitly permitted configuration output; it cannot generate a grant. Not a universal representation of every kind of permission. |
| `TagGroup(Tag, Group)` | Replicated config EDB grouping opaque tags. | Reusable optional IFC vocabulary, with app-owned membership. Grouping alone has no deny, threshold, exclusivity or audit semantics. |
| `Auditor(A)` | Replicated config EDB designating auditors. | App-specific role relation, not a kernel role. Authority and effective configuration version must be explicit. |
| `AuditGoal(Group, T1, T2, T3)` | Replicated config EDB describing a three-part audit goal. | App-specific. Preserve its present arity for Nova migration; do not make every app's goal a three-element tuple. |
| `AuditReceipt(A, Tag)` | EDB imported at Board by the protocol from an auditor's local coverage. | App-defined summary imported through a generic authorized export/import mechanism. Board is a configured route, not a hardcoded destination. |
| `DependsOn(Mout, Min)` | IDB at sender, derived from receive/send/order evidence. | Fixed IFC foundation for the selected dependency policy. Not a model-authored opportunity to omit causal inputs. |
| `Propagated(M, Tag)` | IDB from trusted source tags, imported envelope tags and dependency inheritance, in each local store. | Fixed IFC foundation. Translator can refer to it but must not replace source/import bridges or weaken propagation. |
| `Knows(P, Tag)` | IDB at P from successful receipts and message labels. | Fixed IFC foundation for tracked received knowledge. Does not mean semantic knowledge of every fact in the world, or knowledge from arbitrary uninstrumented tools. |
| `DenyReceive(P, M)` | Recipient-local IDB consumed by `settle`. | Reserved kernel decision hook. Translated constraints may derive it; the runtime owns the matching, refusal and cleanup semantics. |
| `Audited(Tag)` | IDB at local auditor after receipt; also reconstructed from imported receipts at Board. | App-specific coverage semantics. Translation may define it; admissible exports and receipt trust are declared separately. |
| `Finished(Group)` | IDB restricted to Board today. | App-specific goal/result. No privileged kernel meaning. Evaluate at configured observers with sufficient authorized evidence; do not silently join all stores. |

Current evidence: [schema and rules](../apps/nova/src/policy.ts), [placement and transfers](../apps/nova/src/protocol.ts), [event capture and gate](../apps/nova/src/runtime.ts), [local evaluation](../apps/nova/src/local-store.ts), [configuration](../apps/nova/src/config.ts).

### Capabilities and groups

Predefining `HasCap` supports a common authorization mechanism. It does not create any capability, choose who holds it, or imply that every deployment needs capabilities. Nova's `hr_review` and the grants to HR and Auditor A are configuration supplied by the app authority. `Requires(nova_hiring, hr_review)` expresses a policy requirement; it is a different authority operation from granting that capability. If translation proposes this configuration, it must be validated as a permitted requirement change and recorded with the policy, not executed as arbitrary EDB writes.

A gate needs a defined configuration snapshot. For an initial single-host implementation, evaluate against the current committed local configuration version. A remote implementation must specify the required freshness and revocation behavior; a locally absent grant is meaningful only with a valid authoritative snapshot. Replication is an explicit protocol operation, not a Datalog join into an authority's store.

`TagGroup` is general enough to reuse for grouping labels, but its presence must not trigger hidden enforcement. Nova supplies the membership, the limit of three distinct tags, and the Board exception. `AuditGoal` is not a substitute for group membership: the former describes desired coverage, the latter the scope of an exposure restriction. Tags outside a particular audit goal can still participate in the same confidentiality group. Multiple group membership, ungrouped labels and unknown labels need explicit application semantics. Today's Nova skips the grouped restriction for tags without membership; extraction must not silently advertise stronger behavior. A future profile can require a registry at ingestion if that is the intended policy.

In the proposed protocol, historical receipts should certify an event at its accepted policy/configuration version. Today's two-argument Nova receipt does not carry that version metadata; it must be added to the protocol record/envelope during extraction. Removing an auditor's role later does not retroactively invalidate a previously accepted receipt under the current Nova policy. Checking the current `Auditor` relation again when consuming a historical receipt would add a restriction, as the earlier model experiments showed. Retroactive revocation, if desired, is a separate policy with an explicit representation.

## Interface sketch

These are proposed responsibilities, not exported APIs today. Keep principal binding and administrative observation separate from the agent-facing action surface.

| Boundary | Trusted adapter/runtime responsibility | Agent-visible intent |
| --- | --- | --- |
| Bind a principal context | Resolve authenticated identity and select its local store; isolate it from other stores | No ability to select another identity |
| Ingest a source / update config | Validate source or configuration authority; attach labels or publish versioned configuration | No direct fact-assertion privilege |
| Observe a successful read/compute input | Record actual consumed artifacts; the Nova profile conservatively uses all successful earlier receipts | Request a tool/read or submit an output, not choose which dependencies count |
| Send | Capture sender from context, resolve recipient, obtain an artifact/label snapshot, create pending delivery and export an envelope | Recipient and message/output |
| Receive and deliver | Authenticate/deduplicate envelope, stage allowed imported facts, infer locally, check designated deny, commit delivery through the framework boundary | Payload becomes readable only after acceptance |
| Inspect / simulate | Query a permitted local store or explicitly authorized observer view with the same rules and protocol version | Queries and hypothetical actions, without mutation |

A conceptual adapter call is `receiver.receive(envelope, deliverToInbox)`. The callback must not release content before the gate. Delivery success and `Received` must share an appropriate commit boundary; a callback by itself is not a distributed transaction. For a database-backed inbox use a transaction/outbox arrangement appropriate to that adapter. For uncertain remote delivery, retain an attempt identifier and an explicit recovery state; never pretend a network failure proves no delivery occurred.

Envelope semantics must include immutable message identity, sender/recipient bindings, payload identity, the exported labels and the relevant protocol/policy identifiers. A real remote transport must bind these fields to an authenticated origin and reject tampering/replay according to the delivery contract. Today's Nova uses a trusted in-process host and label snapshots; it has not implemented this network envelope security or cross-process recovery.

Do not expose a general `assert(Received(...))` or `assert(HasCap(...))` tool to agents. If an app needs self-reported observations, declare a distinct claim relation with issuer and verification semantics. Trusted runtime events, verified application facts and unverified claims must remain distinguishable.

## Translation and placement for Nova P1–P5

Translation should consume the actual enabled predicate/protocol contract, not an independently maintained prose approximation. The contract fixes authoritative EDB sources, legal locations, fixed foundation rules, permitted generated heads, execution hooks and already supported export/import channels. The model still generates policy Datalog directly; no return to the earlier three-template IR is required.

| Policy | Fixed mechanism needed | Generated policy contribution and deployment location |
| --- | --- | --- |
| P1: retain tracked information across sends | Trusted ingestion; committed receive history; conservative dependency capture; source/import/propagation rules | Identify and require the IFC mechanism. Record this policy's dependence on its invariants rather than inventing weaker propagation rules. |
| P2: required capabilities | Trusted grants, valid local config snapshot, imported tags, receiver gate | Missing-capability denial at the recipient; validate the hiring-tag requirement as authorized policy configuration. Board receives no implicit bypass. |
| P3: three distinct same-group tags | Local received-knowledge and incoming-label foundation | Recipient-local denial rules covering one/two/three incoming tags, pairwise distinctness, group membership and the explicit Board exception. |
| P4: denied messages do not disclose or create knowledge | Receive lifecycle, guarded delivery, removal of temporary inputs, success-only receipt facts | Require these runtime guarantees and trace them to P4. A Datalog denial alone cannot establish payload isolation or rollback. |
| P5: audit coverage and completion | Successful receive events and an authorized summary export/import channel | Local audit-coverage rules and completion from available receipts at configured observers. The current app routes receipts to Board; this is configuration, not a runtime privilege. |

The resulting executable artifact should bind policy rules and any narrowly permitted policy configuration to a versioned mechanism set, a predicate/placement contract and permitted transfer channels. Every policy needs an explicit disposition: generated rules, satisfaction by a named runtime guarantee, or unsupported/ambiguous. That is deployment metadata and traceability, not permission to omit a policy silently. The current prototype's “each policy must have nonempty Datalog” condition cannot represent P1/P4 satisfied by fixed mechanisms; it must be revised before this design is implemented.

Locality validation must check body access as well as head placement. A rule for P must not read Q's local `HasCap` or `Knows`, including through helper predicates or recursion. A summary imported by a declared route is the available EDB; no evaluator may substitute a global union to make a missing join work. New model-defined helper IDBs can be allowed only with validated schema, location and dependency rules. They cannot create arbitrary new EDB sources, networking operations or delivery gates.

The model may propose a need for an additional observer/export route, but a missing authorized route blocks installation or requests clarification. Merely predicting that a rule would be easier at a global observer must not authorize exporting another principal's data. For the first Nova extraction keep the current routing/locality contract and validate generated rules against it. Later expose a constrained, reviewable deployment-plan proposal if real apps require it.

Keep receive-gate semantics explicit. Nova currently permits a valid, well-formed receive when no `DenyReceive` is derived; the generic action API requires explicit Allow and no Deny. Neither policy can be silently selected by naming a predicate. Preserve Nova's deny-based receive semantics in its profile, while treating validation, invalid-envelope and engine failures as failures that cannot deliver.

## Type-state machines

Use a small runtime-owned protocol state machine for message delivery. Nova already stores `pending`, `delivered` and `denied`; make these transitions an explicit part of the generic receive contract. An invalid/missing envelope or evaluation failure must not become a delivered state. Only the success transition creates the successful-receive observation. Pending or denied payloads never enter the receiving model's context. Concurrent receives evaluate against the state at their actual commit boundary.

When a framework callback has external effects, a conceptual `delivering`/recovery state may be needed. A failed or timed-out callback must not blindly reset to pending if an external delivery might already have happened. Exact transitions and recovery acknowledgments belong to the adapter's delivery contract, not a model-authored state diagram.

Business-resource type-state is a separate optional mechanism: e.g. `draft → reviewed → published` for a document. The kernel supplies safe transition checking/commit and observation hooks; the app defines types, states, transitions and policy guards. An allowed transition is subject to authorization; transition reachability alone grants no permission. State and success events change only when the wrapped operation succeeds under the defined transaction boundary.

The current [lifecycle module](../runtime/src/lifecycle.ts) contains all of the following relations:

| Predicate | Current behavior | Proposed role |
| --- | --- | --- |
| `ResourceType(Resource, Type)` | EDB, one type per resource checked by validator | Trusted app registry input to optional lifecycle support |
| `ResourceState(Resource, State)` | EDB, one current state checked by validator | Runtime-maintained committed state after integration; agent cannot assert success |
| `Transition(Type, Action, From, To)` | EDB, ambiguous target transitions rejected | App-owned machine definition, optionally proposed by translation and validated |
| `ActionTaken(Event, Resource, Action, From, To)` | EDB accepted as history; current evaluator does not execute actions or establish that the history is genuine | Runtime observation of a committed transition after integration |
| `EnabledAction(Resource, State, Action)` | IDB from type/transition graph, independent of current `ResourceState` | Structural candidate action. Must join the current state and pass authorization before execution |
| `ReachableState(Resource, From, To)` | IDB graph reachability | Analysis aid, not policy-aware feasibility or a liveness guarantee |

This module is not currently connected to an action executor or to Nova resources. Do not describe it as existing lifecycle enforcement. For Nova's next step, formalize message typestate first and keep business-resource machines optional. Confidentiality depends on combinations of accumulated tags and is better expressed by Datalog relations than by enumerating a state for every possible knowledge subset. Likewise, `Finished` is a derived coverage query; it need not be a mandatory terminal workflow state.

Predicate argument typing (`Principal`, `Message`, `Tag`, `Capability`, etc.) is distinct from resource typestate. Both are useful, but neither is fully enforced by today's string-based fact representation. Do not conflate TypeScript type annotations with runtime validation of untrusted JSON facts.

## Other currently exposed relations

The generic action prototype supplies configurable names for `Request/4`, `Allow/1` and `Deny/2`. They are reserved action-gate roles, not aliases for Nova's receive events. `Request` is runtime-created temporary input; policies can derive Allow/Deny; denial wins and missing Allow refuses. `Actor`, `Public`, `Confidential`, `Reader`, `Role`, `Suspended`, `Read` and `Accessible` in Document Vault remain application relations, even where the concepts could later use a reusable capability/lifecycle module. `QueryResult` and parser sentinels are internal query machinery, not application predicates or remote fact types.

This inventory covers Nova, the new generic action interface, Document Vault and the shared lifecycle module. The older five-principal native chat path is a separate compatibility profile with `Carries`, `DerivedFrom`, `New` and `Deny`; its schemas must not be conflated with Nova during extraction.

## Proposed next implementation slice

1. Make the Nova predicate/protocol contract the single source for schema, fixed rules, placement, permitted transfers and translator context. Keep today's names/semantics initially; defer naming cleanup and generalized audit arity.
2. Extract the principal-scoped messaging protocol into runtime, parameterized by this contract. Nova supplies principals, source authorities, capabilities, group membership, audit goals, receipt routes and scripted behavior. Grokbot supplies its UI/framework adapter.
3. Install a translated Nova policy artifact into a fresh session. Gate, local inference, Why/What-if/search, replay and checkpoint restore must carry the same policy/protocol identity. A feature not yet adapted must reject explicitly rather than fall back to reference rules.
4. Compare reference and translated Nova through actual send/receive transitions, including denied-body isolation, envelope loss, multi-label propagation, pending interleavings, cross-store injection, duplicate attempts, failed delivery and historical receipts. Add an independent adapter conformance test to show the boundary is not Grokbot-specific.

Keep the old one-shot results immutable. A translator that now relies on fixed IFC mechanisms solves a changed task; its results must not be presented as a direct accuracy improvement over the earlier prompt that asked the model to generate those mechanisms.

[Distributed protocol primitives and minimal-plan RQ](distributed-protocol-rq.md) develops placement, export projections, typestate and bounded plan synthesis.
