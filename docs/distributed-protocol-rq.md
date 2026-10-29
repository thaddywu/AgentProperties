# Policy translation and distributed protocol synthesis

Design/RQ proposal, 2026-10-28. The notation below is not implemented syntax. The current Nova runtime has explicit stores, transfers and local rule evaluation; it does not synthesize or optimize those choices. Its fixed foundation and app-specific reference rules are now separated in code and the demo UI.

## What the translator targets

An application extends a fixed, enabled foundation with application relations and constraints. The foundation specifies trustworthy events, basic IFC propagation, capability semantics and the effects of designated decisions. The app supplies resource types/identities, configuration values, policy constraints and goal predicates. Built-in relation schemas do not supply application grants or membership facts.

The target artifact can eventually have two parts:

1. Policy Datalog over the enabled foundation and declared app relations.
2. A validated deployment protocol: fact placement, rule placement, event-triggered exports/imports, lifetimes and snapshot/completeness requirements.

The model may propose the second part within allowed placement and disclosure constraints. It does not gain authority to copy private facts to an arbitrary peer or weaken the foundation. Keep the generated rules and protocol plan linked to the same version for execution, queries, provenance and replay.

## Small protocol primitives

The following is illustrative notation for discussion. `@P` denotes a store location; P in a tuple is an ordinary argument until a declaration explicitly binds it to a principal. Variables in an export must be bound by the triggering event or a positive local relation. `_` is an anonymous match variable; avoid giving `*` two conflicting meanings as both wildcard matching and exported projection.

```text
store Received(P, M) at P       lifetime durable
store Incoming(P, M) at P       lifetime pending(M)
store HasCap(P, C) at P         authority capability_config

eval Knows(P, T) at P
eval DenyReceive(P, M) at P     hook receive(M)

on send(S, D, M):
  export Propagated@S(M, T)
      as TransportTag@D(M, T)
      lifetime pending(M)
      retain on successful_receive(D, M)

on new_coverage(A, T):
  require Auditor@A(A)
  export Audited@A(T)
      as AuditReceipt@Observer(A, T)
      for Observer in configured_audit_observers
      lifetime durable_receipt
```

The event `new_coverage` above is a proposed adapter/runtime trigger for newly established coverage, not an existing freely assertable EDB. It must bind an actual local result and record its origin/configuration version. Historical receipts are accepted observations, not automatically retracted replicas of a potentially non-monotonic live view.

The message export matches the current M, not every message in the sender's history. A rule such as “export `A(P, _)`” can mean selecting matching local tuples, but the plan must still say which columns are retained, who receives them, what predicate they become, when they expire and who may issue them. Projection can remove fields necessary for a later join or for verifying the issuer, so these are semantic obligations rather than formatting choices.

Locations for `TransportTag(M, T)` and `Propagated(M, T)` cannot be guessed from the first argument: M is a message, not a principal. They use the envelope's recipient or the current store context. Similarly, `Audited(T)` can be derived independently at several peers. Only explicitly imported summaries permit a local consumer to use remote evidence.

An export query reads its permitted source store. It is not permission to run a global query. Metadata can itself disclose information: exporting a `Knows` relation, tag list or proof may reveal facts the recipient is not allowed to learn. The plan needs authority/disclosure constraints in addition to Datalog safety and arity checks.

## State machines and inference

In current Nova, the message lifecycle participates through `Incoming`, `Received` and imperative guards in `send`/`settle`. No `ResourceState`, `Transition` or `EnabledAction` relation occurs in a `DenyReceive` rule. The separate lifecycle module has inference rules for graph enablement and reachability, but no connected action executor.

One future encoding could derive an invalid-state denial from a trusted current resource state and permitted transition relation, then compose it with IFC and access-control denials. Transition validity is necessary but not sufficient authorization. Resource state must be committed by the runtime/adapter after the actual transition, not asserted by model output. Unknown or invalid protocol state can also abort before policy inference; not every runtime failure needs to be represented as a business-policy Deny fact.

Do not enumerate every possible set of known tags as a typestate. Use the message state machine to enforce operation ordering, and Datalog to express relationships across messages, tags, capabilities and application facts.

## Defining “minimal”

Proposed research question: given a policy, trusted observation sources, supported query/goal workload and permitted disclosure/placement constraints, can we synthesize a low-cost distributed storage/inference/transfer plan that preserves the required observable behavior?

The optimization target must be explicit. Candidate costs include retained tuples/bytes over time, transmitted bytes, number of network rounds, recomputation, and disclosure to additional principals. These objectives can conflict. An inclusion-minimal plan (no selected component can be removed) is not necessarily a globally minimum-cost plan. A fixed weighted objective, lexicographic priorities or a Pareto frontier are possible evaluation choices; there need not be one universal minimum protocol.

Required behavior includes allowed as well as denied deliveries, payload isolation, queries at their permitted locations, the selected provenance/replay requirements and task progress. Rejecting every message is a cheap but invalid “optimization.” Deleting historical inputs may preserve today's deny decision while breaking tomorrow's send-label propagation, Why or replay. Likewise, retaining only `Knows` can suffice for some future gates but lose the provenance required by other workloads. The requested observables determine what can be discarded or summarized.

A reference centralized evaluator can be an offline oracle over a precisely defined event/configuration snapshot; it is not an executable global-store implementation of the distributed gate. For Nova, compare against the existing per-principal protocol and its reference transition outcomes, including all relevant pending-message schedules. State the intended semantics first rather than assuming that arbitrary global Datalog closure is the specification.

## Absence, revocation and in-flight messages

`not HasCap(P, C)` is meaningful only when the deciding store has a valid, complete authoritative capability snapshot for the relevant decision version. A delayed grant is not evidence of absence. The required revocation/freshness model must be specified; missing completeness evidence should block/fail the decision under the protocol rather than turn into a successful proof of a negative fact.

The same problem affects “allow if no DenyReceive”: absence of a denial is safe only after the required local inputs and rule strata have been evaluated for that attempt. A state that might later receive missing input cannot automatically stand in for the intended decision snapshot. Pending receives also require sequencing or another concurrency contract so that two individually acceptable receives do not both commit using the same stale local knowledge.

Existing work provides context rather than a claim of novelty: [WebdamLog](https://arxiv.org/abs/1304.4187) studies distributing Datalog-style data and programs among autonomous peers. [Keeping CALM](https://arxiv.org/abs/1901.01930) discusses the connection between monotonic logic and coordination-free distributed consistency. Our proposed question adds application enforcement boundaries, authorized disclosure, observable query/provenance requirements and protocol-plan synthesis. These papers do not by themselves establish an optimality or correctness result for this proposed interface.

## A bounded first experiment

1. Use Nova's hand-reviewed rules and current protocol as a semantic baseline. Specify mandatory observer queries, permitted receipt routes, allowed storage sites and configuration-version semantics.
2. Enumerate a finite set of choices: local recomputation versus retained derived summaries, permitted config replication subsets, and authorized message/receipt projections. Never offer arbitrary sharing of `Knows` as a valid way to reduce cost.
3. Let translation propose a plan, then statically validate schema, writer, locality, exports and negation-completeness requirements. Evaluate cost and behavior using a deterministic executor/searcher, rather than accepting an LLM assertion that its plan is minimal.
4. Compare fixed-plan translation, LLM-proposed plans and bounded exhaustive/search-selected plans. Measure false allows/denies, goal/query/provenance agreement, cost, rejected/unsupported plans and synthesis effort. Keep a held-out trace corpus, including delayed configuration, dropped envelopes and interleaved receives.
5. Report optimality only within the enumerated plan space and checked workload/domain. Passing sampled traces is conformance evidence, not a proof over all apps and all asynchronous executions.

This separates two questions: whether natural language was translated into the intended policy, and whether a distributed implementation preserves that policy at lower cost. Either can fail independently.

## Current demo changes and copy

The Rules dialog now has `Built-in` and `Nova reference` views. Each shows `EDB · input schema`, source kinds, `IDB · derived schema` and its executable inference rules. `App-supplied values` reveals configuration separately. The fixed section says “Fixed IFC and capability rules. Configuration values come from the app.” The app section says “Handwritten Nova rules; the app-specific translation target.” Inspector rows identify `Built-in schema` or `Nova schema`; a built-in predicate such as `DenyReceive` can still be derived by app-specific rules.

These labels distinguish runtime invariants, app configuration and handwritten reference policies during a demo. The explanation is revealed inside the Rules dialog instead of adding persistent explanatory copy to the main screen. Removing the source distinction would imply that configuration values are built in or that the active Nova rules were already generated. This change does not switch the Nova translator prompt or install generated Nova rules.
