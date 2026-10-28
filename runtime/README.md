# Policy runtime

Application-neutral function-free Datalog evaluation, safe query parsing and validation, bounded native Soufflé evaluation/provenance, and resource-lifecycle relations. This package has no dependency on Grokbot, Nova, model providers or the UI.

Callers supply input facts and rules. The AST, predicate names and evaluation semantics are unchanged by the extraction. `runSouffle` and `explainSouffle` retain the existing native resource limits; `queryDatalog` retains bounded, read-only policy queries.

The application interface in `src/application.ts` adds a generic in-process action gate. Applications supply a trusted binding and a translated bundle; the runtime does not import Nova, Grokbot, model adapters or app-specific predicates. [Document Vault](../apps/document-vault/README.md) exercises this interface with real document callbacks.

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

Inspection while an operation is in flight throws; await the operation first. Callbacks must not await another operation on the same session. A failed callback leaves runtime observations unchanged, but the runtime cannot undo an external database write or network action already performed by that callback. Applications own external transactions, authentication, persistence, factual freshness and any access-control filtering of query/proof results. Sessions are process-local and do not coordinate multiple workers. Recreate a session from the same explicit bundle and trusted inputs to replay it; there is no automatic persistence or hot replacement.

This interface handles observable action authorization. It does not infer trustworthy facts from prose, instrument arbitrary source code, detect semantic information leakage, or prove future task completion. The argument roles are descriptive strings with arity validation, not a rich entity type system. Acceptance cases cover only their supplied examples.

Nova-specific local stores, message transport, receive gates, prevention search and completion search remain in `apps/nova`. The older native chat protocol remains in Grokbot. Both keep their existing execution paths; installing a generic bundle does not change a Nova session. General action-space planning is not part of this new interface.
