# A staged application-port workflow

The optional application-port adapter enforces four host stages: discovery,
binding, rules and instrumentation with verification. Discovery and binding use
bounded, data-only model calls over supplied source. The coding CLI handles rule
generation and instrumentation. The host owns stage artifacts, hashes,
validation, permitted writes and progression. `CodexPort.translate` delegates to
this harness. Independent back-translation and alignment remain subsequent
entries and are not automatically run by that method.

The workflow below separates seven responsibilities within those four stages and
the later review steps. It describes implemented constraints and their limits,
not a completed application evaluation. The harness surrounds the porting coding
agent; it does not replace the target application's agent runtime. For commands, see
[porting](../porting.md); for fact meanings, see
[observations and translation](observations-and-translation.md).

## Stage artifacts and progression

| Host stage | Required artifacts | Enforced checks |
| --- | --- | --- |
| Discovery (`inventory`) | `inventory.json` and retained attempts | Data-only model call with a strict JSON schema; no file tools or application execution. Named Python functions/methods and exact signature parameters exist; evidence uniquely quotes their source. Boundaries have supported kinds and explicit identity/effect/outcome descriptions. |
| Binding (`binding-plan`) | `binding-plan.json`, `binding-freeze.json`, host-generated `policy_port/binding.py` | Data-only planning leaves the candidate unchanged. Validate parameter-path shapes/types, source quotes, observation registries, selected stock EDB, explicit static role/group/grant/FSM configuration, empty custom IDB/invariants, P-numbered policy dispositions and agent-write authority entries. Freeze accepted artifacts and framework hashes. |
| Rules (`rules`) | `policy_port/rules.dl` and its accepted hash | Only the existing rules file is writable. Retain exact configuration and existing framework schemas. Reject new EDB/IDB declarations, stock redeclarations and observed-fact seeds; compile and execute bounded native initialization before freezing the accepted program. |
| Instrumentation and verification (`instrumentation`) | Additive patch, tests, `checks-*.json`, captured gate traces and `translation.json` | Factory/rules/source/framework remain protected. Reject unchanged planned source symbols; validate structural changes and restricted constructors. Run native tests, require native evaluation evidence for planned gates and actual source execution for observation producers, and check frozen runtime contracts/rules, approved inputs/actions, trace completeness and both applied/blocked outcomes. |

`workflow.json` persists accepted stage hashes and final verified/failed status.
Every stage has bounded repair attempts with retained outputs and validation
failures. Accepted artifacts are checked on reuse. A modified freeze is rejected;
it is not silently regenerated. Changed binding assumptions require a new binding
version/run and revalidation of dependent rules, hooks and tests.

These checks constrain artifacts and the executions captured by tests. They do
not prove that the inventory found every path or that producer descriptions are
true. A hash establishes unchanged content, not correct content. The seven
responsibilities below describe what a port must establish; agent authority is
planned in binding and wired during instrumentation, not a fifth host session.

For the first two stages, `CodexPort.plan()` calls the optional provider-neutral
`Connection` transport with a strict JSON response schema. The host supplies a
bounded selection of original Python/JSON source and policy text, the shared
catalog, runtime guide and parameter-binding implementation. Binding planning
also receives the accepted inventory; repair calls receive the prior draft and
validation errors. The model has no file tools and cannot execute the app in
these stages. The host saves its response and usage, then validates the returned
object against actual source. Structured output constrains the response shape;
it does not establish correct evidence or semantic mappings.

For a planning error tagged with `BindingError.sections`, the repair schema permits
replacing only those rejected top-level sections. Each changed section is a
complete replacement; every retained section is returned as `null`. The host
merges retained content from the previous draft, rejects unauthorized section
changes, then revalidates the entire merged object, including cross-references.
Section repair preserves unaffected draft content; it does not bypass whole-plan
validation or authorize changes after the binding freeze.

The coding CLI starts at rule generation, where only `rules.dl` is writable, and
continues in instrumentation with protected source, factory and rules. Thus the
four host stages do not correspond to four unrestricted coding-agent sessions.

## 1. Discover actual boundaries

Start from an immutable source snapshot and the original policy. Inspect tool
registration and dispatch, agent-to-agent messages, model-context construction,
model-output consumption, final reply delivery and background actions. Follow
indirect paths to their effects: a tool wrapper is insufficient if another path
can invoke the same backend directly.

The host validates boundary kinds `tool`, `message`, `model_context`, `reply` and
`background`, parses Python source without importing application code, and checks
that the named function/method and ordered signature parameters actually exist.
Its exact unique quotation must lie inside that function. This source validation
does not infer every effect or automatically discover omitted boundaries.

For each boundary, record the source file and symbol, call path, actual arguments,
actor/identity source, recipient, data crossing the boundary, original guards,
business effect, success/failure shapes and asynchronous/background behavior.
Distinguish a message being generated from being delivered, and a model receiving
context from a reply being shown to a user. A research assistant's retrieved
document, internal model context and exported report are different disclosure
boundaries even when they share a data object.

Inventory the real provenance producers. `Source` records direct origins;
`DependsOn` records conservative dependencies supplied by instrumentation or
application records. A coding agent's inference about likely dataflow is a plan
for instrumentation, not a captured dependency fact. List missing observations,
identity sources and unmediated paths rather than infer them from prose.

The copied runtime guide's **Semantic boundaries for port-in** section is required
at discovery, binding, rule generation and instrumentation. Freeze producer
authority, versioned object identities, direct input membership, granularity,
scope, timing, lifetime and capture completeness in the existing plan descriptions.
`DependsOn` records possible influence at that declared granularity. For a model
output the adapter records all inputs actually supplied through its context,
including retained history; unrelated task history is not automatically a parent.
Runtime-agent self-declarations cannot supply or erase authoritative edges.
Cumulative task exposure and exact message-content lineage have different meanings
and must not be conflated. A missing edge in incomplete capture cannot establish
clean content. Verify both forbidden flows and permitted paths, including task
separation and policy exceptions, against the actual implementation. The host
freezes the descriptions but does not mechanically prove their truth or completeness.

Supervising the porting coding agent's own file and tool calls protects the port
workspace. It does not establish that every effect of the target app is mediated.
Only target boundary analysis and execution evidence can support that claim.

## 2. Freeze the binding and evidence

Freeze one contract per call kind, including overloads or branches with different
effects. The accepted JSON plan contains `mechanisms`, `calls`, `observations`,
`derived`, `invariants`, `requirements` and `agent_writes`. Preserve the following
meanings and review obligations within that plan and its source evidence:

Several obligations below are carried in descriptions and quotations rather than
separately typed fields. Requiring a description does not mechanically verify its
authority, completeness or factual correctness.

| Contract part | Required contents |
| --- | --- |
| Call | Actual registered name, function/signature, argument names/defaults, encoding, actor and recipient binding, effect location and original guards. |
| Inputs | Relation/field/metric name, ordered arguments and types, units, cardinality, key, current/history meaning, session/resource/tenant scope and missing/invalid behavior. |
| Producer | Exact source operation, authority, collection timing, validation, freshness, replacement/deletion, restart and concurrency behavior. |
| Requirement | Exact policy span, interpretation, Datalog rules to generate, adapter duties, claim/decision authority, delegated checks and unsupported/ambiguous gaps. |
| Evidence | Source revision and content hash, repository-relative file, symbol, exact quoted span and its offsets/line location; generated artifact references remain distinct from source evidence. |
| Gate plan | Gate action and parameter mapping, prerequisite observations, success predicate, post-success writes, failure/uncertainty treatment and bypasses. |

The schema applies to generic `Field` names as well as domain predicates. A field
called `owner` still needs a producer and a scope. A metric called `amount` still
needs a unit. Reusing one subject ID across sessions requires an explicit global
identity contract. An assumed singleton field cannot silently receive two rows.

The current harness fixes EDB and IDB schemas to the selected shared catalog.
It generates Allow/Deny clauses and source-backed static configuration, not new
predicates. Bind observations through declared Field definitions, numeric types,
fixed units and optional observation-time references. Keep derived=[] and
invariants=[]. Conditions requiring unavailable schemas/language constructs remain
explicit gaps; adapters cannot conceal them in policy booleans or helper rows.
Event is a shared observation identity, not a generated seed.
Agent-write entries permit existing decision operations;
they cannot invent a new decision schema or expose host-only observations.

Per-action parameter paths must be valid names whose underscore-joined encoding
matches the planned parameter name. The host checks those shapes and exact source
quotes, plus simple dispatcher branches with literal action names. It does not
prove every path corresponds to the claimed value in arbitrary source code.
Likewise, a unique producer quote proves where text occurred, not that the source
has the claimed authority, timing or semantics. P-numbered policy sections must
each have a quoted `supported`, `partial`, `unsupported` or `ambiguous`
disposition; that structural coverage is not semantic coverage of every clause.

For example, a synthetic `send_payment(account_id, amount_cents, recipient_id)`
binding must name those actual parameters and the application's source of account
ownership, amount, review delivery and receipt. It cannot replace them with a
vague `SafePayment` input. A missing review delivery path is an adapter gap or an
unsupported lifecycle requirement, even if Datalog can express the desired join.

Preserve exact source provenance for every assumption. Pin source policy and
application evidence independently; use exact policy spans for requirements and
exact implementation spans for producers and gates. Public examples must use
synthetic data; full private run artifacts need not be published to make the
contract reviewable. Never include credentials or machine/account identifiers.

The host derives `observationContract` and `callContract`, generates the protected
`make_policy` factory and freezes inventory, binding plan, factory and framework.
Runtime observation checks reject unregistered names/units and conflicting
single-valued fields; `one` means at most one value, not required presence.
Runtime call checks restrict actions, supplied parameter names and encodings;
they do not require every declared parameter to be supplied. See the
[contract details](observations-and-translation.md#frozen-observation-and-call-contracts).
Changed units, producers or interpretations require a new binding version/run.
The separate rules-only translator accepts an already trusted binding and does
not invoke repository discovery.

## 3. Design and compile rules for the fixed binding

Give rule generation the fixed binding, source requirements and installed shared
mechanisms. Generate domain clauses while preserving the requirement dispositions,
adapter duties and gaps. Reuse the shared foundation rules
without rewriting their meanings or making a derived helper synonymous with final
authorization.

The rules-stage mount permits writing only policy_port/rules.dl. No .decl/.input
or new EDB/IDB schemas are admitted. Use existing shared predicates and inline
ordinary owner/version/record joins. PrincipalGroup configures membership and
InGroup supplies its existing closure. Static configuration must exactly match
the frozen binding and cannot seed Field or Event. Literal field references must
belong to the frozen registry. The host compiles and freezes the rule program;
instrumentation cannot revise it. Missing expressibility is reported rather than
replacing a missing helper with hidden tuples or Python authorization logic.

Place policy decisions in Datalog: permissions, ownership joins, thresholds,
approval validity and lifecycle conditions. Adapters can normalize inputs and
compute policy-independent quantities. A Python boolean such as `Eligible`,
`Safe` or `Approved` cannot stand in for generated policy logic. Existing guards
may remain, with their delegated role and coverage limits recorded.

Compile before editing the app. Check arity/types, input versus derived ownership,
keys, allowed rule heads, bound variables, finite function-free syntax and
stratification. Verify that authorization rules consume the intended call fields,
units and resource scope. Static validation does not establish semantic fidelity;
runtime tests and independent reading remain separate stages.

## 4. Place gates and observations per call

Make a concrete patch plan for every inventoried call. For supported synchronous
Python functions, `@policy` binds the real function arguments and reads the
reported caller from `caller_context`. Where an existing dispatcher carries a
trace ID, use the supported explicit name/arguments mapping. Authentication still
belongs to the host. Async annotations and `Policy.acall` await the original
callback on the caller loop while native gates and synchronous hooks run in a
worker. Respect worker-compatible transactions, per-policy serialization,
non-reentry and cancellation/unknown-outcome semantics in the runtime guide.
Background execution and other transports still need explicit integration.

Construct every generated policy instance through the host-owned
`policy_port.binding.make_policy`, including development tests. The factory pins
mechanisms, invariants, observation contract, call contract and the rules file.
The host rejects changed factory/rules and recognized alternate framework
constructor imports. These static restrictions are not a proof against arbitrary
or malicious Python behavior.

Use this temporal sequence for each operation:

1. Obtain prerequisite state/time/confirmation from its actual producer. Ingest it
   through trusted host APIs before the gate when the decision depends on it.
2. Evaluate the request with actual parameters. Invoke the original callback only
   after explicit allowance with no denial.
3. Interpret the original result using the application's real success criterion.
   Stage confirmed result observations inside the guarded body or supported result
   hook; publish them only with the confirmed outcome.
4. Preserve original failure and uncertainty. Do not fabricate success, certify
   rollback after a possible external effect, or silently fall back to a simulator.

`Request` describes the current attempt. It is not automatically a successful
`Event`. An observed event can reuse the request ID, but its producer must write
it and its actual parameters/outcome. Post-success facts support future gates.
The framework's local staged EDB does not make an external backend and the policy
checkpoint a distributed transaction. State race, persistence, reconciliation and
bypass limits for the actual deployment.

### Execution monitoring and student harness

Instrumentation installs observation hooks together with EDB producers and gates.
Observe the actual dispatcher before checks, its original arguments/result, real
message sends/receipts, visible model outputs and background effects. Preserve
original application behavior. Participant types come from source responsibilities,
never names. Runtime/transport/simulator components are not automatically agents.
Do not duplicate native tool/model logs inside opaque state payloads.

The student harness owns reset, scenarios, external test inputs, app startup and
independent task-completion checks. Its CLI delegates repetitions, lifecycle and
export to workbench.runner.main. Port-in may instrument application runtime code;
it must preserve evaluation scenarios/checks. Applications with runtime code mixed
into a harness need a clean module boundary or an injectable observer interface.

The shared recorder owns IDs, order, JSON/JSONL serialization and embedded native
evidence. One export produces a directly readable timeline; no per-app Inspector
converter is required. Gate/monitor association uses explicit trace and call IDs.
Matching nested policy wrappers reuse the observed operation; nested implementation
operations carry parent IDs and stay under All events. Missing or ambiguous gate
associations are not guessed. Separate-process execution needs adapter-side wiring.

A coding-session timeout does not itself invalidate a retained candidate. If static
boundaries/frozen artifacts remain valid, run host-owned native verification before
paying for another coding turn. Only actual passing checks can accept that candidate;
timeout is never converted directly into a passing result.

## 5. Expose only policy-granted agent recording authority

This responsibility is recorded in `binding-plan.json` under `agent_writes` and
implemented in the instrumentation stage; it has no independent coding session.

Keep trusted `Policy.put/delete/update` inside host adapters. When policy empowers
an agent to record a decision, expose a principal-bound FactTool with an explicit
input allowlist and rules for put/delete. Check authorization against pre-write
state, constrain the exact operation and issuer, and record real operation
contents/version. The agent cannot grant itself permission by inserting the fact
being checked. Host-only `Field` and `Event` remain unavailable to it.

FactTool is a general framework interface for existing trusted input contracts.
The current port harness fixes stock EDB and does not create custom approval
predicates. Prefer an app's existing decision operation when it supplies the
required lifecycle; absent decision infrastructure remains a gap.

Unverified self-statements have no dedicated fact-writing tool. Ordinary messages
can retain them without granting observation or decision authority. Provenance
capture requires actual instrumentation or explicit application records.

A decision requires a real decision subject and delivery path. If the application
does not show the operation to its authorized reviewer, report the missing path.
Do not add business tools, solvers, confirmation screens, roles, approval rounds
or replacement agent workflows to complete the port. A policy can give an agent
decision authority; it cannot make an invented confirmation an observed fact.

## 6. Validate, execute and repair within the failed stage

Verification and its repairs are part of the fourth host stage. A model-driven
port run means the coding agent produced and repaired the port using real model
requests. It does not mean the target app's own LLM scenarios ran. Native callback
tests with explicitly labeled offline external/model fixtures are development
evidence and can validate a port without claiming app-agent task completion.

The host validates the patch against the original snapshot. Preserve original
statements, signatures, guards, ordering, documents, tests, configuration and
assets under the additive port contract. Structural checks can reject rewrites;
they do not prove that arbitrary helper code has no side effects. Limit edit
scope and test the actual callbacks and effect boundaries.

Scaffolding and tests around dummy callbacks do not establish instrumentation of
the original app. For every boundary referenced by supported/partial requirements, the host
compares the named original and candidate Python symbols and rejects an unchanged
AST. A changed symbol alone does not prove that a gate is correctly placed, so
the execution checks also require evidence from those same implemented boundaries. Unsupported-only inventory entries remain gaps and do not require gates.

Run real native Datalog for positive cases, attempted violations and boundary
cases. Compare original and protected effects: legitimate workflows must still
work, and denied operations must have no forbidden effect. Include cases driven
by the binding: wrong actor/scope/unit, missing/stale observations, contradictory
set-valued fields, changed review contents, write self-authorization, callback
failure and uncertain outcomes, where applicable. Do not replace the engine,
gate, authorization results or business callbacks to make tests pass.

The host checks captured gate trajectories for the frozen observation and call
contracts, the accepted rule hash, absence of unapproved input predicates, and
in-scope actions for effects. Evidence must be complete under the capture contract
and demonstrate both `applied` and `blocked` outcomes.

`CodexPort.check` mounts the frozen inventory read-only into the native batch
worker. At native evaluation time, the worker matches actual Python stack frames
to the inventory's source files and qualified symbols, reporting counts as
`nativeBoundaryCalls`. For `@policy`, the checked wrapper's bound body function
also identifies the boundary because authorization precedes entering its body.
`check_recordings` requires a nonzero count for every boundary referenced by
supported/partial requirements. Unsupported-only inventory entries are excluded.
Counts are collected by the worker, not accepted from a generated test's claimed coverage.

These checks provide placement and native-execution evidence within the planned
inventory. A blocked decorated call can count without executing its business
body; a native evaluation count is not proof of a successful business effect.
The applied/blocked requirement remains aggregate, not a positive/negative pair
for each action. Neither the counts nor structural changes prove exhaustive
mediation, semantic fidelity, correct producer behavior or coverage of every
policy clause and bypass.

Deterministic offline fixtures are development evidence. Label mocked external
dependencies and keep them separate from application-completion evidence. A
completion claim about the target app requires its original agent implementation,
prompts, tools and native scenario entry point, with real model requests when the
app requires them. An unavailable real dependency produces a failed/blocked run;
it does not justify substituting scripts or forced agent decisions.

Preserve each failed candidate, prompts, source/artifact hashes, diffs, commands,
results, trajectories and usage privately. The harness repairs within a stage and
rejects later changes to frozen plans/rules. Classify a failure before repair:
discovery/binding changes need a new version/run; rule changes must be accepted
before instrumentation; hook, authority and runtime failures belong to the fourth
stage. Automatic semantic diagnosis or dependency-driven replanning is not
implemented. Keep exposed development failures distinct from held-out
evaluation. Passing tests means only that those tests passed under their stated
conditions; it does not prove policy equivalence or complete mediation.

## 7. Independently read back, then align

`CodexPort.backtranslate()` and `CodexPort.review()` are later independent entries.
`CodexPort.translate()` ends after port verification. The adapter CLI's explicit
`--stage all` composition can invoke translation, reverse reading and alignment;
this composition does not move source policy into the reverse session.

Start a fresh read-only session with actual rules, binding meanings, runtime,
configuration and implementation evidence. Exclude original policy documents,
forward plans, coverage claims and tests. The reader traces each implemented
behavior through its gate, derived conditions and actual input producers. It must
describe delegated guards, missing producers and bypasses alongside the affected
guarantee. An intended stage plan is not evidence that a hook exists.

Group auxiliary projections and other helpers with the consuming gate's business
condition. Trace them back to actual inputs, but do not turn each intermediate
relation into a separate policy requirement or imply that a helper grants an
independent permission.

Freeze those descriptions before a separate alignment pass receives the original
policy. Alignment can identify matched, weaker, stronger, missing or ambiguous
behavior; it cannot rewrite descriptions to fit the source. Repairs create a new
candidate and a new independent reading. The rules-only translator's independent
rule reading covers rules, while the executable port's reverse pass also examines
implementation; their evidence scopes are different.

## Current implementation and next steps

| Capability | Current evidence and limit |
| --- | --- |
| Existing-binding translation | [pipeline.py](../../src/policyweave/policy_adder/pipeline.py) validates an injected binding, generates requirements/rules with bounded repair, pins artifacts and reads rules independently. It does not discover the binding. |
| Staged application adaptation | [harness.py](../../src/policyweave/policy_adder/harness.py) enforces four stages with persisted artifacts, bounded repairs, binding/factory/rule freezes and native trace checks; [codex.py](../../src/policyweave/policy_adder/codex.py) supplies data-only `plan()` calls for inventory/binding and isolated coding-CLI sessions for rules/instrumentation. |
| Source-backed fixed binding | [binding.py](../../src/policyweave/policy_adder/binding.py) checks Python symbols/signatures, unique evidence spans, fixed stock EDB, the fixed schema, requirement dispositions and agent-write entries, then generates the factory. It does not prove all source-to-field semantics or exhaustive boundary discovery. |
| Change validation | [preservation.py](../../src/policyweave/policy_adder/preservation.py) and host boundary checks constrain additive instrumentation and protected assets. They do not prove absence of helper side effects or all application bypasses. |
| Planned-boundary execution | [batch_worker.py](../../src/policyweave/adapters/batch_worker.py) records native evaluations from gate stack frames or the trusted decorator's bound body, and actual source calls for `role: producer`. The harness requires the corresponding evidence for each supported/partial boundary and rejects unchanged source symbols in that implemented scope. Unsupported-only inventory entries remain gaps. This establishes scoped placement/execution evidence, not guaranteed business effects or complete mediation. |
| Independent review | [back-translation](../../src/policyweave/back_translation/README.md) and [viewer alignment](../../src/policyweave/policy_viewer/README.md) separate implementation reading from source comparison. Model descriptions still need review. |
| Target-app execution | Existing profile-specific runners and captured trajectories supply scoped evidence. A generic adapter does not automatically supply every app's native runner, reset/replay or authoritative observations. |

Remaining work includes stronger source-to-field semantic checks, per-action and
per-clause effect coverage, application-specific producer/gate conformance and
explicit versioned replanning when assumptions change. Authenticated identity,
backend reconciliation and full mediation still need application evidence.
Implementation of the harness is separate from evidence that a particular
model-driven port succeeds. This guide makes no such experimental success claim.
