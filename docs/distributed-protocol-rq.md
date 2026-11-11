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

eval HasReceivedTag(P, T) at P
eval Deny(M, message_policy) at P     hook receive(M)

on send(S, D, M):
  export MessageTag@S(M, T)
      as TransportTag@D(M, T)
      lifetime pending(M)
      retain on successful_receive(D, M)

on new_coverage(A, T):
  require Auditor@A(A)
  export Covered@A(T)
      as Covered@Observer(T)
      for Observer in configured_audit_observers
      lifetime durable_receipt
```

The event `new_coverage` above is a proposed adapter/runtime trigger for newly established coverage, not an existing freely assertable EDB. It must bind an actual local result and record its origin/configuration version. Historical receipts are accepted observations, not automatically retracted replicas of a potentially non-monotonic live view.

The message export matches the current M, not every message in the sender's history. A rule such as “export `A(P, _)`” can mean selecting matching local tuples, but the plan must still say which columns are retained, who receives them, what predicate they become, when they expire and who may issue them. Projection can remove fields necessary for a later join or for verifying the issuer, so these are semantic obligations rather than formatting choices.

Locations for `TransportTag(M, T)` and `MessageTag(M, T)` cannot be guessed from the first argument: M is a message, not a principal. They use the envelope's recipient or the current store context. Similarly, `Covered(T)` can be derived independently at several peers. Only explicitly imported summaries permit a local consumer to use remote evidence.

An export query reads its permitted source store. It is not permission to run a global query. Metadata can itself disclose information: exporting a `HasReceivedTag` relation, tag list or proof may reveal facts the recipient is not allowed to learn. The plan needs authority/disclosure constraints in addition to Datalog safety and arity checks.

## State machines and inference

In current Nova, the message lifecycle participates through `Incoming`, `Received` and imperative guards in `send`/`settle`. No `ResourceState`, `Transition` or `EnabledAction` relation occurs in a `Deny` rule. The separate lifecycle module has inference rules for graph enablement and reachability, but no connected action executor.

One future encoding could derive an invalid-state denial from a trusted current resource state and permitted transition relation, then compose it with IFC and access-control denials. Transition validity is necessary but not sufficient authorization. Resource state must be committed by the runtime/adapter after the actual transition, not asserted by model output. Unknown or invalid protocol state can also abort before policy inference; not every runtime failure needs to be represented as a business-policy Deny fact.

Do not enumerate every possible set of known tags as a typestate. Use the message state machine to enforce operation ordering, and Datalog to express relationships across messages, tags, capabilities and application facts.

## Defining “minimal”

The optimization preserves semantics; it does not choose a weaker policy or a smaller subset of query answers. For each admissible execution trace and corresponding logical snapshot t, let E(t) be the complete EDB and R the full rule program. Let C_full(t) = closure(E(t), R) be the full-copy baseline. Each principal P maintains E_P(t), evaluates its assigned rules R_P, and participates in the declared transport protocol to obtain C_P(t). The required equality is:

```text
union over P of C_P(t) = C_full(t)
```

This includes every predicate in the compared vocabulary, not only Deny, Finished or a selected projection. Each principal need not hold the complete closure by itself. Tuple locations remain explicit protocol metadata; union comparison removes duplicate tuples, while local decision checks retain locations.

Union equality alone is insufficient: at every actual decision location and before its protected effect, the local decision must equal the full-copy decision for the same logical input/configuration snapshot. A Deny fact at the wrong peer after payload release fails this requirement. Successful/denied delivery traces, payload visibility and relevant goals must remain the same. The target covers all legal positions and continuations, not just the current snapshot. Asynchronous internal steps require an explicit correspondence between baseline and distributed snapshots; an implementation may not release payload while waiting for inputs needed by the baseline decision.

Minimize local retained EDB and rule copies subject to these equivalence constraints. Report facts/bytes and rule copies separately until a cost function is chosen. Communication and recomputation can be additional costs, but are not a replacement for the closure-preservation requirement. An inclusion-minimal plan (nothing can be removed) is not necessarily globally minimum-cost. The minimum can depend on admissible inputs, protocol actions and the chosen cost measure.

Full-copy is a diagnostic specification, not permission for the actual application to disclose all facts to all agents. Existing disclosure/authority constraints remain constraints on the optimized plan. Neither discarding required closure facts nor rejecting every message is a valid optimization. Preserving the set of inferred facts also does not automatically preserve a particular proof tree, historical reconstruction or latency; those observables need their stated requirements as well.

Keep two comparisons separate: (a) translated policy versus golden policy, and (b) an optimized distributed execution versus full-copy execution of the **same** policy. A wrong translation can have a perfectly correct distributed implementation. Nova's snapshot checker evaluates the full-copy baseline only as an offline diagnostic; the real gate still reads its receiver's local store. The UI reports closure-union differences and each pending recipient's Deny comparison, plus stored EDB copies versus full replication. These are finite witnesses, not a universal equivalence proof or a demonstrated minimum.

## Absence, revocation and in-flight messages

`not HasCap(P, C)` is meaningful only when the deciding store has a valid, complete authoritative capability snapshot for the relevant decision version. A delayed grant is not evidence of absence. The required revocation/freshness model must be specified; missing completeness evidence should block/fail the decision under the protocol rather than turn into a successful proof of a negative fact.

The same problem affects “allow if no Deny”: absence of a denial is safe only after the required local inputs and rule strata have been evaluated for that attempt. A state that might later receive missing input cannot automatically stand in for the intended decision snapshot. Pending receives also require sequencing or another concurrency contract so that two individually acceptable receives do not both commit using the same stale local knowledge.

Existing work provides context rather than a claim of novelty: [WebdamLog](https://arxiv.org/abs/1304.4187) studies distributing Datalog-style data and programs among autonomous peers. [Keeping CALM](https://arxiv.org/abs/1901.01930) discusses the connection between monotonic logic and coordination-free distributed consistency. Our proposed question adds application enforcement boundaries, authorized disclosure, observable query/provenance requirements and protocol-plan synthesis. These papers do not by themselves establish an optimality or correctness result for this proposed interface.

## A bounded first experiment

1. Use Nova's hand-reviewed rules and current protocol as a semantic baseline. Specify mandatory observer queries, permitted receipt routes, allowed storage sites and configuration-version semantics.
2. Enumerate a finite set of choices: local recomputation versus retained derived summaries, permitted config replication subsets, and authorized message/receipt projections. Never offer arbitrary sharing of `HasReceivedTag` as a valid way to reduce cost.
3. Let translation propose a plan, then statically validate schema, writer, locality, exports and negation-completeness requirements. Evaluate cost and behavior using a deterministic executor/searcher, rather than accepting an LLM assertion that its plan is minimal.
4. Compare fixed-plan translation, LLM-proposed plans and bounded exhaustive/search-selected plans. Measure false allows/denies, goal/query/provenance agreement, cost, rejected/unsupported plans and synthesis effort. Keep a held-out trace corpus, including delayed configuration, dropped envelopes and interleaved receives.
5. Report optimality only within the enumerated plan space and checked workload/domain. Passing sampled traces is conformance evidence, not a proof over all apps and all asynchronous executions.

This separates two questions: whether natural language was translated into the intended policy, and whether a distributed implementation preserves that policy at lower cost. Either can fail independently.

## Current demo changes and copy

The Rules dialog has five views: `Runtime`, `Nova input`, `Translated`, `Reference` and `Prevention`. Runtime shows the builtin predicate schemas, inference rules, protocol placement/transfers and app-supplied configuration values. Nova input shows the exact checked-in Markdown; imported artifacts retain their own exact input snapshot. Translated shows per-policy builtin/extension coverage, generated rules, model identifier and inherited protocol. Reference preserves handwritten app rules and the complete fixed protocol. Prevention runs actual send/settle comparisons in fresh sessions and a separate full-copy diagnostic on the selected snapshot.

`Start reference session` and `Start translated session` explicitly replace the demo with a new initial session. No hot policy replacement occurs inside an existing history. The active mode and content identity are visible. Failed artifact checks leave the existing session intact. Generated extensions can write Deny, Covered and Finished, but cannot replace the fixed propagation/knowledge rules, write input facts, change trusted configuration or replace the protocol. The versioned artifact is revalidated when restored from a checkpoint; query, Why, What-if, search and replay use the same installed rules.

The key copy is “Fixed protocol inherited; protocol synthesis is not implemented.” and “Checks passed; semantic equivalence is unproven.” These distinctions are necessary to avoid presenting fixed protocol reuse as agent-generated deployment or finite tests as proof. “Prevention uses fresh sessions and baseline configuration. Closure comparison uses the selected snapshot.” distinguishes the two experiments. Details and evidence are revealed inside the dialog rather than adding persistent explanations to the main interface. The active Reference/Translated label remains visible because it changes which rules enforce delivery.

The legacy whole-policy one-shot remains available. The new `--nova-extension` experiment provides the fixed foundation and protocol to the model, excludes golden app rules and acceptance cases, and exports a reloadable artifact. It does not synthesize a new protocol or run a minimizer. See the [Nova walkthrough](../apps/nova/README.md).

Current Nova scope: audit-summary transport has been removed. Local closures exclude Finished; the global observer computes only Finished rules on their union. The implemented comparison therefore checks the local union plus observer outputs against full-copy, and checks each pending local gate separately. The universal placement/channel-synthesis question remains a research target; Finished does not exist at every principal. The bounded placement experiment below is now executable.

## Implemented bounded placement experiment

`runtime/src/protocol-planner.ts` now enumerates admissible placements of declared shareable inputs and existing rules, preserving full-copy closure, pending local denials and declared query observations on each supplied snapshot. It uses exact enumeration with a budget, emits program/witness/search hashes, and deploys through `applyProtocolPlan`. Channels and source authorities are fixed constraints; the cost is stored input tuple copies across witnesses plus deployed rule copies plus replicated tuple copies. Private capability facts cannot be offered as shareable inputs.

The [Nova port command](../apps/nova/README.md#backend-neutral-port-and-fsm-experiment) generates 190 distinct witnesses, enumerates 96 plans and preserves four observer/local queries. Reference and saved translated policies each admit 24 plans. Reference cost changes from 19,833 to 10,329; translated cost from 19,839 to 10,335. These are equal-weight experimental tuple/rule counts, not measured latency or network bytes. Both selected plans are installed and run with delivery callbacks and a report FSM. Results: [reference](evaluation/nova-ports/reference.json), [translated](evaluation/nova-ports/translated.json).

The Rules dialog and `--nova-extension` translation still inherit their fixed protocol; this new optimizer is a separate explicitly invoked command/API. UI text about that translation mode therefore describes its own path. The finite optimum does not cover unobserved configurations/traces, general transport-channel synthesis, proof-tree preservation, asynchronous timing or durable multi-worker execution.
