# Nova Budget Audit: distributed Datalog policy

This version adds a server-backed, isolated App 2 episode to Rakazo. Enable **Use Our Policy** to open it. Original Rakazo chats and policy sessions have independent state. Switching views preserves both; leaving policy mode pauses the episode after an already-started step finishes. It never changes a session's policy mode. All interface text is English.

## Scope

Five principals participate: Executive Board, Procurement, Facility, Hiring, and Auditor A. The application fixes the task order and destinations; the connected default model generates requests, replies, and the report. A shared backend protocol decides every delivery. Decisions are not model judgments or scripted outcomes.

Policy agents run through Rakazo's Pi adapter with no tools, implicit builtin tools, native chat history, sandbox files, shared memory, or subagents. This is a bounded experimental runtime, not a global security patch for arbitrary original Rakazo bots. Original mode remains unrestricted by this policy. The web interface also works in Electron's web surface; the native mobile app does not yet expose the policy console.

The authenticated observer can inspect all principals and denied payloads. Agents cannot read that observer state. API sessions belong to one user and space. Only the server can initialize sources, record dependencies, attach facts, or advance the protocol; RPC clients cannot submit replacement states or facts.

There is **no sanitization or declassification**. The policy models explicit artifact dependence conservatively. It does not prove that an LLM cannot guess a secret or measure timing/control-channel leakage. A generic delivery-failure notice is intentionally visible to the auditor; it contains neither the blocked body nor its restricted facts.

## Facts and their lifetimes

| Fact | Created by | Location and lifetime | Transported? |
| --- | --- | --- | --- |
| `Carries(M,P,C)` | Trusted source initialization, then Datalog propagation | Source/output owner's store; successful receiver's store | Yes, attached to that immutable artifact |
| `DerivedFrom(Y,X)` | Runtime records every artifact supplied to a computation | Computing principal's persistent store | No |
| `Received(A,M)` | Receive enforcement after permission succeeds | Receiver's persistent store | No |
| `Knows(A,P,C)` | Local Datalog closure over Received and Carries | Receiver's persistent store | No |
| `Incoming(A,M)` | Receive gate | Temporary candidate evaluation | No |
| `New(A,M,P,C)` | Stratified evaluation against existing Knows | Temporary candidate evaluation | No |
| `Deny(A,M,R)` | Receive rules, with rule identifier R for inspection | Temporary candidate evaluation; observer retains a decision witness | No |

`M` identifies an immutable artifact within a session. A delivery has a separate directional message ID. Its pair counter is shared by both directions, counts denied attempts, and is saved atomically. For example: `msg_A_to_B_1`, `msg_B_to_A_2`, `msg_A_to_B_3`. The UI shows the delivery ID and attached `Carries` facts naming the artifact; resending an artifact would preserve its identity.

`Knows` means conservative policy knowledge, not a claim that the recipient literally saw the secret sentence. A budget-only reply derived from a restricted reason counts as knowing that component.

## Execution protocol

1. **Create.** Trusted initialization creates three public budget artifacts ($8M, $3M, $5M), three restricted Nova reason artifacts, and a public audit assignment. Only reason artifacts receive initial Carries labels. This is source ingestion, not a Board LLM computation over all of Board's history. Board can receive without the combination restriction, but cannot sanitize.
2. **Compute.** The runtime retrieves all artifacts owned by or successfully delivered to the principal, including previous outputs and runtime notices. Exactly that complete set is supplied as model context. The runtime independently records DerivedFrom edges for every input. Local Datalog derives output Carries; model wording cannot remove or forge tags. An empty or failed result aborts the step.
3. **Send.** Verify the sender can access the immutable artifact, assign the next shared pair counter, and record the send event. The logical envelope contains routing/identity, payload, and only the artifact's Carries facts. The sender's Knows, Received, and dependency graph do not travel.
4. **Evaluate receive.** Under the session's database row lock, combine the receiver's current local facts with temporary Incoming and candidate Carries. Compute the stratified closure and denial rules before exposing the body to the receiver.
5. **Allow.** Add the artifact to the receiver's accessible set, add Received and transported Carries, and close local Knows. Commit them together with the trace and revision.
6. **Deny.** Leave the receiver's store exactly unchanged: no payload, Received, Carries, or Knows from the candidate is committed. Record the attempted delivery and rule witness only for the observer. The application can subsequently issue a separate generic failure notice.

Every step is one database transaction. Same-session operations serialize; the expected revision makes duplicated/retried advance requests no-ops. Model calls have a 45-second timeout inside a 60-second transaction. If a call or transaction fails, no step state is committed, though the provider may already have processed/billed the request. Sessions persist across browser reloads. **New session** creates another row; completed sessions remain stored.

## Executable rules

The UI renders the actual rule AST from `packages/core/src/policy/datalog.ts`; the same AST drives the finite, function-free, stratified evaluator. The notation below omits the diagnostic argument on Deny for readability.

```prolog
Carries(Y,P,C) :- DerivedFrom(Y,X), Carries(X,P,C).
Knows(A,P,C) :- Received(A,M), Carries(M,P,C).
New(A,M,P,C) :- Incoming(A,M), Carries(M,P,C), not Knows(A,P,C).

% R3a: three new components
Deny(A,M) :- New(A,M,P,C1), New(A,M,P,C2), New(A,M,P,C3),
             A != board, C1 != C2, C1 != C3, C2 != C3.
% R3b: two new components and one already known
Deny(A,M) :- New(A,M,P,C1), New(A,M,P,C2), Knows(A,P,C3),
             A != board, C1 != C2, C1 != C3, C2 != C3.
% R3c: one new component and two already known
Deny(A,M) :- New(A,M,P,C1), Knows(A,P,C2), Knows(A,P,C3),
             A != board, C1 != C2, C1 != C3, C2 != C3.
```

All three components must belong to the same project. Duplicate or already-known labels do not count as new knowledge. Starting from valid source state, no non-Board principal can acquire all three Nova components through receiving.

## The rejection to inspect

Board distributes budgets before reasons. Auditor A issues all three requests before receiving department replies, so those requests are public. Each department then answers using its complete history, including its restricted reason. Even a one-sentence budget-only answer inherits that department's label.

Procurement's reply adds the first component. Facility's adds the second. Hiring's `msg_hiring_to_auditor_a_2` brings a third: **R3c denies it**. Select that receive event and compare Auditor A's Before/After local stores: they are identical. A later failure-notice event is distinct. The final report is generated without Hiring's blocked body, inherits only Procurement and Facility labels, and is allowed to Board. The audit remains incomplete.

The event timeline exposes Create, Compute, Send, Receive, and Notice events. Every event snapshots all five stores. Select an event, a principal, and Before/After to inspect historical facts and accessible artifact bodies. The decision inspector includes temporary inputs and matched rule witnesses.

## Running and verification

Use the existing Rakazo model connection and data-sharing consent. This first version supports API-key and OpenAI-compatible credentials. Choose your model in Original Rakazo, enable Use Our Policy, then select **Run episode** or **Next step**. The protocol's deterministic tests require no provider.

```sh
pnpm --filter @rakazo/db exec prisma migrate deploy
pnpm --filter @rakazo/db generate
pnpm exec vitest run packages/core/src/policy/protocol.test.ts packages/adapters/src/pi-runtime-cancellation.test.ts
pnpm --filter @rakazo/api check
pnpm --filter @rakazo/web check
pnpm --filter @rakazo/web build
```

The migration adds only `policy_sessions`; it does not rewrite original bots, chats, or messages. A normal source build includes the new API and UI. The optional `infra/compose/Dockerfile.policy` layers the changed sources onto a matching published Rakazo image for a local Compose installation; use `docker-compose.policy.yml` after the normal image Compose file.

Validation covers all three denial rules, project separation and duplicate labels, transitive propagation, unauthorized sources/forwarding, exact computation inputs, immutable snapshots, shared direction counters, builtin-tool isolation, transaction rollback/retries, and session ownership. The browser test checks message facts, unchanged denied-receive stores, mode preservation, the rule viewer, and the narrow-screen inspector. A live local OpenAI-compatible run also completed through the UI's New session / Run episode controls: seven model computations, 43 trace events, one R3c denial, and an incomplete report delivered to Board.
