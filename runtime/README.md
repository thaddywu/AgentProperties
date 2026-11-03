# Policy runtime

Application-neutral function-free Datalog evaluation, safe query parsing and validation, bounded native Soufflé evaluation/provenance, and resource-lifecycle relations. This package has no dependency on Grokbot, Nova, model providers or the UI.

Callers supply input facts and rules. The AST, predicate names and evaluation semantics are unchanged by the extraction. `runSouffle` and `explainSouffle` retain the existing native resource limits; `queryDatalog` retains bounded, read-only policy queries.

`messaging-policy` supplies the fixed messaging/IFC/capability vocabulary and six foundation rules used by Nova. Application grants, tag-group membership, principals, exposure limits, audit roles and goals remain app-owned. Nova composes the foundation with its five handwritten reference rules. The shared `messaging` and `distributed` modules now implement event capture, principal-local closure, label transfer and receive gates. Nova supplies only its domain profile, checkpoint migrations and analyses. `primitives` exposes readable canonical names from that same foundation; the legacy names remain compatible with saved artifacts.

The application interface in `src/application.ts` adds a generic in-process action gate. Applications supply a trusted binding and a translated bundle; the runtime does not import Nova, Grokbot, model adapters or app-specific predicates. [Document Vault](../apps/document-vault/README.md) exercises this interface with real document callbacks.

The [application porting contract](../docs/application-porting-contract.md) specifies the target boundary for other backends: policies and builtin/FSM configuration, a validated execution profile, and implemented trusted EDB producers. Its illustrative manifest is not supported by the version-1 binding. `RuntimeBinding.mechanisms: ["fsm"]` enables protected transitions with current-state checks, authorization, serialized callbacks, success-only state replacement/history and explicit uncertain-outcome recovery. The binding must declare `LIFECYCLE_PREDICATES`; application rules cannot override this foundation.

## Connect an application

```ts
import { createPolicySession } from "@rakazo/policy-runtime/application";

// binding comes from the trusted application adapter; bundle is translation output.
const session = createPolicySession(binding, bundle, trustedInputFacts);
const result = await session.execute(
  { actor: authenticatedActor, action: "read", resource: documentId },
  async () => documentStore.read(documentId),
  [{ predicate: "Read", args: [authenticatedActor, documentId] }],
);
// Only the allowed result has a value. A denied request never invokes the callback.
```

The version-1 binding declares arbitrary input/derived predicates, their arities and meanings, plus three configurable gate predicate names with fixed argument roles:

- Request: `(requestId, actor, action, resource)`, a transient input created only by the runtime.
- Allow: `(requestId)`, a derived explicit permission.
- Deny: `(requestId, reason)`, a derived refusal that overrides permission.

No Allow means refusal. Parse, schema, safety, stratification, acceptance-case and evaluation-limit failures throw; they never invoke an action. Rules cannot write input predicates. The adapter may supply only declared non-request input facts. Rules, facts and queries reuse the existing bounded TypeScript evaluator, with encoded constants preserving uppercase names and quotes. Native Soufflé is not needed for this interface.

`compileApplicationPolicy(binding, datalog)` validates rules and runs the binding's independent cases, then returns a JSON bundle containing the source, binding and content hash. At least one allow and one deny case are required. The app revalidates the artifact against its own trusted binding on session creation. The hash detects content changes; it is not a signature or a proof that a policy expresses the original text correctly.

| Session operation | Behavior |
| --- | --- |
| `execute(intent, callback, commitInputs?)` | Serializes gate evaluation, callback and observation commit; checks current state when execution reaches the queue. |
| `check(intent)` | Preview only; never an authorization token. `execute` always evaluates again. |
| `query("?- Relation(X).")` | Read-only query over current session facts and the installed policy; rejects injected facts or rules. |
| `why(fact)` | Proof tree for a present fact; bounded explanations mark truncation. Decision results also include gate evidence. |
| `whatIf(intent, hypotheticalInputs)` | Evaluates a complete hypothetical input snapshot without committing it. |
| `replaceInputs(facts)` | Queued trusted-adapter state replacement, validated before commit. |
| `snapshot()` | A copy of committed inputs. Transient requests and derived facts are never persisted. |

Inspection while an operation is in flight throws; await the operation first. Callbacks must not await another operation on the same session. A failed callback creates no success observations, but the runtime cannot undo an external database write or network action already performed by that callback. For FSM sessions, ordinary failures add `ResourceRecovery` and block further actions on that resource; a trusted `EffectNotAppliedError` certifies no effect. `reconcile(attemptId, "applied" | "not_applied")` resolves a confirmed outcome without repeating the effect. Recovery bookkeeping is process-local. Applications own external transactions, authentication, persistence, factual freshness and any access-control filtering of query/proof results. Sessions are process-local and do not coordinate multiple workers. Recreate a session from the same explicit bundle and trusted inputs to replay it; there is no automatic persistence or hot replacement.

This interface handles observable action authorization. It does not infer trustworthy facts from prose, instrument arbitrary source code, detect semantic information leakage, or prove future task completion. The argument roles are descriptive strings with arity validation, not a rich entity type system. Acceptance cases cover only their supplied examples.

Nova-specific reference/translated extensions, checkpoint migration, prevention search and completion search remain in `apps/nova`. Local stores, transport staging and receive gates are shared runtime mechanisms. The older native chat protocol remains in Grokbot; installing a generic action bundle does not change it. General action-space planning is not part of this interface.

## Connect a messaging backend

Use `createMessagingProfile` to select principals, source authorities, configuration and app relations/rules/placement. Direct or translated Datalog source can use `parsePolicyRules(source)` with application `ruleEncoding: "parsed"`; it rejects ground facts and embedded queries before schema/foundation/locality validation. Use `createBackendPort({ profile, observations, deliver })` to register authoritative versioned EDB producers and the real delivery callback. Hand the agent only `port.bind(authenticatedPrincipal)`: `send`, read-only local `query` and `accessible`. Trusted source ingestion and recovery remain on the administrator surface.

The port serializes refresh → sender closure/export → receiver closure/gate → callback → successful receipt. Incomplete/unversioned snapshots block dispatch; complete replacements remove revoked grants. Denial never calls the delivery function. A delivery timeout enters reconciliation rather than an automatic retry. Process-local replay protection does not replace backend persistence, transactions or authenticated remote transport.

`primitives` exports `Knows`, `AgentHasCapability`, message/source/dependency/denial schemas and FSM schemas. See the [porting contract](../docs/application-porting-contract.md#8-implemented-interfaces-and-primitive-vocabulary) for every argument, writer and alias. `Knows(A,T)` means an observed successful tracked receipt. It is not a semantic classifier.

`protocol-planner` exactly searches declared finite shareable-input/rule placements using witness snapshots, optional local query observations and a tuple/rule/replication cost. It returns scope and program/witness/search hashes. `applyProtocolPlan` deploys it on the same profile. This optimizes placement under fixed message channels and authorities; finite witness agreement is not universal asynchronous correctness or a production latency result.

The [Nova walkthrough](../apps/nova/README.md) includes an executable backend-port and report-FSM trial using either reference rules or a saved translated extension. Grokbot's optional `message-policy-port` adapter maps authenticated runs to this same interface; production-wide host mediation still requires durable composition-root wiring and all relevant input hooks.

## Bounded comparison and testing

`bounded-equivalence` compiles parsed function-free, stratified rules to a Boolean CNF comparison, supporting recursion, negation and inequalities. Callers supply a `FiniteComparison`: trusted input/derived schema, reference/translated rules, observable predicate names, required/optional EDB tuples and optional EDB-presence clauses. A caller-provided `SatSolver` handles CNF; no solver dependency is required by the runtime core. The actual Nova adapter uses an offline MiniSat build in a killable subprocess.

`finite-domain` supplies evaluator-based exhaustive and seeded testing with that same contract. Counterexamples are projected to selected outputs, replayed and deletion-shrunk under the declared constraints. Unknown outcomes, empty domains and incomplete testing are explicit; equality is always limited to the finite catalog. See [commands, statuses and evidence](../apps/nova/evaluation/README.md#bounded-sat-and-configurable-testing).
