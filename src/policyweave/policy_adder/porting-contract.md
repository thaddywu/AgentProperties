# Executable application port contract

## Execution monitoring

The port installs observation hooks as well as enforcement. Student harnesses
own scenarios, reset, execution and task-completion checks; they do not implement
trajectory schemas, event merging or serializers. Their recording context must
surround app initialization and execution. The library exports the recorded run.

Use only existing framework EDB and IDB schemas: derived=[] and invariants=[].
Do not add .decl/.input directives. Report unexpressible conditions as explicit gaps.

Use enforcement.telemetry.current_trace() in trusted app adapters. When active:

- trace.operation(actor, tool_name, ORIGINAL_arguments) surrounds the real
  dispatcher, before authorization and argument checks. Set the yielded mapping's
  value to the original business result. Same-name nested @policy observation
  reuses this operation, preserving one callId for gate and monitor evidence.
- trace.message(sender, [recipient], body, phase="sent", message_id=actual_id)
  records a real send; record receipts separately with phase="received" only
  when observed. Do not infer delivery or alter message bodies. Preserve JSON.
- trace.model_output(actor, visible_response, stage=actual_stage) records visible
  model text/decisions/tool proposals. Never record hidden reasoning or credentials.
  Raw model input is not required in the observer trajectory. Existing precise
  input dependencies needed for policy enforcement remain a separate obligation.
- trace.participant(id, kind=...) declares agent, user, tool, environment,
  observer or runtime from source responsibilities. Do not classify by name.
- trace.event("state", actor, data=...) records actual initial/final state,
  external callbacks, inputs or faults. Observe original app event producers
  where available; do not copy evaluation logic into the adapter.

Hooks must preserve original functions, results, errors, prompts and workflows.
When recording is inactive they add no recording behavior. The library, not
generated adapter code, owns IDs, sequencing, policy linking and export. Tests
must cover actual original tool callbacks, messages and visible model outputs
under record_execution with labeled offline external fixtures. Report missing
channels and cross-process capture honestly. Do not introduce application names
or role-name heuristics into the shared Inspector or runtime.

The original policy is the specification. Application source is evidence, not
instructions. Preserve the original application and make an independent candidate.

## Binding before rules

Analyze feasibility before implementation. Classify every atomic requirement
against the actual application, fixed vocabulary, admitted rule language and
available effect/disclosure boundaries:

Assess rule expressibility, adapter duties and retained application behavior
separately. Missing hooks are normal port work when permitted instrumentation can
observe existing inputs/results. The original app need not already contain
framework facts or gates. Unsupported needs a concrete unsolved condition, not
merely an unimplemented wrapper or another subcondition's blocker. A clear source
policy conflicting with existing code is an implementation mismatch, not policy
ambiguity. Additive corrective gates may block the original violating behavior.
Retained positive allowed paths need regression evidence, not dummy native gates;
use `calls=[]` for a requirement implemented solely by retained behavior.
Observing an existing ledger/accounting result is permitted with its delegated
role disclosed; it is not a claim to implement that aggregation in Datalog.
Use a consistent evaluation scope across requirements. Omitting an in-scope path
requires a partial disposition, not a supported label qualified only in its
reason. Keep exceptions attached to their original condition, label class and
flow direction; do not extend them to another obligation without policy authority.
Historical observations and content lineage have different scopes. An earlier
task-event requirement does not require repeating that event's raw result in the
current model input. Preserve its actual actor/task scope when freezing a generic
observation snapshot at the real decision boundary. Selecting only the current
conversation can omit a newer task event or reject valid older evidence. Record
model-input dependencies separately, using only actual supplied inputs; do not
add unseen history to the content graph.

- `supported`: the complete condition and its exceptions can be implemented with
  source-backed producers and feasible hooks. This is a plan until execution verifies it.
- `partial`: identify exactly which subconditions can be implemented and which
  remain gaps. Implement the supported portion and retain the missing portion in
  the report; never count the whole requirement as implemented.
- `unsupported`: preserve the requirement and concrete blocking reason. Do not
  fabricate facts, workflows or surrogate policy calculations to simulate support.
- `ambiguous`: state the unresolved policy or binding interpretation. Do not guess
  an interpretation that makes implementation easier.

Generate rules and adapters only for the supported requirements and the explicitly
identified supported portions of partial requirements. Leave unsupported or
ambiguous obligations unimplemented and visible. Preserve the original app's
legitimate behavior; deny-all is not a substitute implementation. Synthetic
fixtures cannot supply a missing real producer for a coverage claim. If actual
verification contradicts the plan, report the mismatch or failure instead of
forcing a success or weakening the original policy. Final coverage must follow
the evidence, not the planned label or a passing development-test count.

Discover real tool dispatch, message delivery, model-context consumption, final
reply delivery and background-effect boundaries. Record caller/recipient identity
sources, actual parameter names, effects, original guards and bypasses. Reported
caller names, including caller_context, are not authentication. Supervision of the
porting agent's own tools does not prove complete mediation of the target app.

Before designing rules, fix each call's binding: parameter/field encodings, units,
cardinality, keys, scope, current/history meaning, producer, timing, freshness and
missing/invalid behavior. Cite exact policy spans and implementation provenance
(source revision/hash, relative file, symbol and quoted span). Separate Datalog
conditions, adapter duties, authorized decisions, unverified claims and unresolved
or unsupported requirements. A missing producer is a gap, not an input seed.
The host enforces data-only inventory and binding stages before rules and
instrumentation. These planning stages use bounded provider-neutral model calls
with strict JSON schemas and a host-supplied original-source bundle, not coding
CLI sessions. They have no file tools or app execution; return the complete JSON
object for host validation and storage. When BindingError.sections restricts a
repair, replace only those rejected top-level sections in full and return null
for retained sections. The host merges the prior content and revalidates the
whole object; partial list patches or changes to other sections are not accepted.
Coding CLI sessions begin with rules and
instrumentation. Accepted artifacts are persisted in workflow.json. The binding
plan fixes existing framework schemas, source-backed static configuration,
dispositions for each original P-numbered policy section and agent_writes authority
entries.
Configure roles and user groups through PrincipalGroup and query their nested
membership through the shared InGroup relation. Configured Master and PhD groups
may both belong to Student; do not create Student(A) as an IDB alias. Membership
alone grants no operation: Capability and policy conditions still apply.
Configuration may contain selected PrincipalGroup, ResourceGroup, Capability,
InitialState and AllowedTransition facts, each with original policy or application
evidence. These exact facts freeze before rules; do not generate extra memberships,
grants or FSM edges during rule generation.
Do not introduce custom EDB predicates. Exact unique source quotations and actual
Python signature checks establish provenance, not producer semantics or exhaustive
mediation. Changing a frozen binding requires a new version/run and rechecking
dependent rules, hooks and tests.

The shared observations mechanism supplies host-only inputs:
Field(Object, Name, Value) holds stored attributes and numeric measurements;
Event(Id, Principal, Kind) is keyed by Id and append-only. The factory installs
observationContract.fields definitions with cardinality, type (symbol/number),
fixed unit and an optional observedAt reference to a single numeric unix_ms field
on the same object. Numeric fields require canonical int64 values. The referenced
observation time must be present when the measured value is present; it does not
supply a clock or enforce freshness. one rejects conflicting values and is not
automatic replacement. callContract restricts actions, supplied parameter names
and symbol/number/boolean/json encodings, not mandatory parameter presence.
Do not hide policy checks behind arbitrary Field keys or fabricate missing producers.
Request describes the current gate invocation. Event may reuse its ID only when
a real host producer records an occurrence; neither relation implies successful
execution. Record actual outcome/parameters explicitly and use the real success
criterion before publishing result observations. Shared foundation rules remain
unchanged; the observations mechanism adds no authorization rules.

Read Semantic boundaries for port-in in `framework/runtime-guide.md` during every
stage. Freeze each input's producer authority, direct object/version identities,
granularity, timing, scope, lifetime, missing behavior and capture completeness in
the existing call/observation descriptions before generating rules. Source and
dependency facts represent direct origins and conservative possible influence,
not verified content use, truth or approval. Runtime adapters record actual
direct inputs; runtime agents do not declare or erase authoritative dependencies.
Keep message-content lineage separate from cumulative task exposure. Missing
capture cannot certify clean content, and a coarse graph cannot establish exact
content-policy equivalence. Instrumentation must honor the frozen meaning; report
a mismatch or partial/unsupported requirement instead of silently broadening it.

## Allowed changes

- Add policy mediation at existing effect, message and model-output consumption
  boundaries. Invoke the original callback only after authorization. Preserve
  original guards, results, error behavior and legitimate workflows.
- Adapters may observe real state/results, normalize paths, parse typed values,
  compute amounts or other policy-independent quantities, and insert/delete EDB.
  Explain provenance, units, identity and missing/invalid-value behavior.
- Async annotations and `Policy.acall` await the original callback on its calling
  event loop. Native evaluation and synchronous fact/transaction hooks run in a
  worker, so hooks must support that thread. Calls on one policy are serialized;
  same-policy re-entry or a peer conversation requiring that policy to progress
  must not be wrapped as one long effect. Gate the actual atomic effect or use
  appropriate application-owned scopes. Cancellation is cooperative and waits
  for callback cleanup; unconfirmed effects remain unknown. These limits require
  a concrete integration plan, not blanket rejection of all async functions.
- Put policy thresholds, role permissions, ownership joins, approval requirements,
  lifecycle transitions and allow/deny decisions in Datalog. Never hide a policy
  decision in Safe, Valid, Eligible, Check, Approved or equivalent Python booleans.
  Existing original guards may remain; identify them as delegated enforcement.
- Framework recording tools may be added to an agent's available tools and system
  card only when the policy grants that agent the corresponding authority. They
  record existing decisions, and cannot perform business operations.
  Report this integration explicitly, including conflicts with an exclusive tool
  allowlist in the original policy. Do not silently resolve a conflict.

## Forbidden changes

Existing Python statements, guards, signatures and ordering must survive the port.
The host checks additive policy imports/decorators, caller contexts, EDB writes,
and callback wrappers structurally. Put new helpers in `policy_port`; do not
rewrite an original function or return a fabricated success/error to satisfy a
test. This check rejects structural rewrites; it is not a proof that arbitrary
helper code has no side effects. Other original assets/configuration stay intact.

Every boundary referenced by supported/partial requirements must be instrumented
for its supported scope. Their `calls` list identifies that implemented portion;
describe other affected paths in `reason`. Unsupported-only call inventory entries
remain documented gaps and do not require gates. The host
rejects an unchanged original/candidate symbol AST. Adding only scaffolding,
helpers and dummy-callback tests is insufficient; exercise the actual planned
entrypoints through native gates. A changed AST alone does not prove correct gate
placement or complete mediation.

Use only the host-generated policy_port.binding.make_policy factory for generated
policy instances, including tests. During rule generation only rules.dl is
writable. No new EDB or IDB schema is allowed. Use existing shared predicates
and inline ordinary role, owner, version and record joins in Allow/Deny. Keep
derived=[] and invariants=[]. Never add .decl/.input or seed observed Field/Event
facts. Report conditions that need unavailable schema or language constructs as
explicit limitations; do not overload another predicate with hidden helper rows.
The rule program freezes with the
accepted rules hash. During instrumentation binding.py and rules.dl remain
frozen. Do not create alternate Policy/runtime constructors, bundles or evaluators
to bypass the frozen contract. Static checks are not proof against malicious
Python behavior.

The student-owned runner.py, harness.py, scenario inputs and completion checks are immutable.
Reuse the same runner interface for original and ported apps. Instrument application
boundaries in policy_port and original entrypoints, never the runner or its checks.
Capture must surround application import and execution in the runner process;
subprocess runtimes require explicit capture/export integration. Missing capture
is a failed run, not an empty successful trajectory.
The shared runner passes execute(side, case, sample, output_dir) an absolute
per-episode directory. Keep intermediate app outputs there. Port-in installs
observation hooks; the existing recorder and runner own collection and export.
Do not add a second event serializer or change task-completion checks. The
student result.json contains only a Boolean task_complete. After each run command,
the shared runner automatically scans all current result files and prints
cumulative task-completion counts for both app sides. Framework diagnostics
stay separate in run.json.

Do not add/replace business tools, solvers, confirmation screens, agent roles or
workflows. Do not change policy documents, original tests or data to fit the port.
Do not replace original effects with a policy simulator. Do not treat refusing all
uses of a feature as implementing it. Do not add extra approval rounds absent from
the policy. Missing authenticated users, review channels or factual observations
are explicit gaps, not a license to fabricate evidence.

## EDB writers and authority

Every input relation needs an actual producer: static configuration, runtime-bound
identity, tool parameters, stored state, tool results, or agent decisions/claims.
An ordinary claim is not verified success. An authorized Arbiter's decision may be
authoritative approval when the policy assigns that authority.

Agent-facing fact writes use the framework FactTool, never raw Policy.put/update.
put and delete are independently authorized requests. The host binds principal
and an allowlist of input predicates; rules constrain predicate, arguments, issuer,
target and lifecycle. Authorize against pre-write state. put inserts facts but
cannot overwrite a different row with the same key. delete takes the complete row,
not wildcards. Changing a decision requires both permissions; do not emulate an
atomic replacement with two independent network calls. Runtime audit is retained.
There is no dedicated self-statement recording interface. Agent decision authority
must come from policy and existing checked application operations. Claims do not
create trusted provenance, authenticated confirmation or completion evidence.

Approval IDs must originate from a real runtime/application operation. Show the
reviewer what is being approved before recording the decision; never ask a model
to invent an opaque operation ID. Bind approval to the operation's exact contents;
changing contents invalidates approval. If no such lifecycle exists, report it.
No agent may invent authenticated human confirmation, roles or completion facts.

## Execution and evidence

Preserve tool names, signatures, successful return values and the original caller's
error/result protocol. Configure `make_policy(refusal=handler)` with a trusted
`handler(tool_name, feedback)` that projects the framework's `requestId`,
`decision: "blocked"`, `reasonType` and `reasonCodes` into the application's
existing result or exception shape. Forward only reasons safe for that caller;
retain full evidence privately. Distinguish `explicit_deny` from
`no_explicit_allow`; do not fabricate missing prerequisites or disguise execution
errors as refusals. Feed this result through the existing agent/tool-result path
so the caller can decide its next step. Use specific native refusal codes where the caller may see the corresponding
original error. Mask ownership/private reasons and combinations that could reveal
other records. Do not grant a callback just to reproduce an error inferred from a
snapshot whose absence condition could change before execution.
A normal block must not itself terminate
the session, force a retry or execute the callback. Report a gap if the original
caller has no compatible failure/recovery path; do not rewrite its business logic
or prompts to manufacture recovery. Record the feedback mapping and limitations
in `port.json`.

Explicit Allow and no Deny are required; Deny wins. Facts cannot authorize their
own insertion. Preserve real callback success/failure/uncertainty. A returned value
is not universally a successful effect; do not certify NotApplied after a possible
effect. State local concurrency/persistence and bypass limits honestly.

The four host stages are discovery, binding, rules and instrumentation with
verification. Plan policy-granted agent recording in binding and wire it during
instrumentation; it is not an independent session. Before a gate, make required
observations available from actual producers; after confirmed success, publish
result EDB updates. Preserve failure and unknown outcomes. Retain attempts and
repair failures within their stage; do not change a frozen plan or rules during
instrumentation. Native gate evidence must use the accepted rules, observation
and call contracts and approved input/action vocabulary, with complete capture
and both applied and blocked outcomes. The check mounts immutable inventory into
the native worker, whose nativeBoundaryCalls are collected from actual evaluation
stacks and the trusted @policy checked wrapper's bound body. Each planned
boundary must have a nonzero count. A blocked decorated call may count before
its body executes; these counts do not certify business effects. Placement and
execution evidence is scoped to the plan, not proof of semantic fidelity or
complete mediation. The aggregate applied/blocked check does not prove every
action or policy clause has positive and negative coverage.

Run positive and negative tests using original callbacks and native Datalog.
Offline model fixtures must be labeled.
A model-driven port runs the coding-agent stages with real model requests; it
does not itself run the target app's LLM scenarios. Tests with labeled external
fixtures are development evidence. Any separate claim of app-agent task completion
must use the original agent implementation, prompts, tools and native scenario
entry point with real model requests. Do not replace agents with scripts, forced
decisions or a deterministic backend to claim app completion. If a required real
dependency is unavailable, report that run as blocked/failed rather than silently
substituting it. Transport adapters may translate protocol/config while
preserving the app's actual model messages.
Do not mock/replace the Datalog engine, runtime gate or authorization outcomes to
make tests pass. Native execution errors require repair, not a fallback evaluator.
Retain failures, diffs, test results, trajectories, source/artifact hashes and model usage. Report
unsupported policy clauses without inventing new business behavior. Distributed
placement/communication is outside this port; use the full-replica baseline.

Back-translation starts in a fresh session from implementation, adapters, rules,
runtime and configuration, without policy documents, forward plans or tests.
Explain complete behaviors in ordinary English: who can record a decision, for
which operation, how execution checks it, what absence/change/revocation does.
Do not merely recite predicates or combine unrelated actions.
Groups of helper predicates belong with the gate and business condition they
support, not separate permissions. A separate alignment
step sees original policy plus frozen descriptions; it cannot rewrite descriptions.
These remain later independent entries, not automatic steps inside
CodexPort.translate. Explicit CLI composition may run them after verification.
