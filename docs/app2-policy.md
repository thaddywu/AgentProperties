# Nova Budget Audit policy in native Rakazo chat

Enable **Use Our Policy** to use the original Rakazo sidebar, bot chats, peer-message view, composer, and background run queue with App 2 enforcement. There is no separate policy dashboard. All interface and generated agent text is English.

- Hover over a message to see its directional delivery ID and attached Carries facts.
- Click the small dot below a message or completed message_bot call to inspect the historical local store. The inspector defaults to After and can show Before, each principal's facts, accessible artifact bodies, and denial witnesses.
- **Start audit** initializes a new episode. **New audit** creates another independent workspace; it preserves the previous one.
- Switching policy off returns to the previous original workspace and chat. Switching back returns to the policy chat. Original navigation hides policy workspaces; policy navigation shows only the current policy workspace. Background runs may finish while another workspace is being viewed, as in original Rakazo.

The first UI-only dashboard and its saved legacy sessions are no longer used by this view. This version creates real native bots, threads, tasks, runs, peer receipts, and realtime events.

## Execution boundary

The native worker detects a policy workspace before acquiring a computer or loading native memory/files/history. It uses the existing connected model resolver and Pi runtime. Policy turns expose **only `message_bot`** and explicitly disable implicit builtin tools. The dispatcher also rejects any other tool name, even if a runtime tries to invoke it. There are no shell, file, browser, web, memory, MCP, or subagent tools.

The existing `message_bot` entry point dispatches policy sends through the transaction-bound receive gate. Calling the unrestricted send path from a policy workspace is rejected. Ordinary Rakazo workspaces retain their normal execution path and tools.

The model sees only its principal's accessible artifacts, the public directory, its own outgoing destinations, and application instructions. It never receives the observer metadata attached to native chat messages. The observer is the authenticated workspace owner and can inspect all five stores and attempted deliveries. Policy inputs are loaded from protocol state, not by replaying observer-visible messages or their annotations.

## Facts and lifetimes

| Fact | Created by | Persistent location | Sent with the payload? |
| --- | --- | --- | --- |
| `Carries(M,P,C)` | Trusted source ingestion, then Datalog propagation | Artifact owner's store and successful receivers | Yes |
| `DerivedFrom(Y,X)` | Runtime, for every accessible computation input | Computing principal | No |
| `Received(A,M)` | Receive gate after Allow | Receiver | No |
| `Knows(A,P,C)` | Local closure over Received and Carries | Receiver | No |
| `Incoming(A,M)` | Receive gate | Temporary evaluation only | No |
| `New(A,M,P,C)` | Stratified evaluation against existing Knows | Temporary evaluation only | No |
| `Deny(A,M,R)` | Receive rules; R identifies the matching rule | Temporary evaluation; observer keeps a witness | No |

An artifact ID is immutable and session-local. Each delivery has a separate directional ID, with a shared unordered-pair counter: `msg_A_to_B_1`, `msg_B_to_A_2`, `msg_A_to_B_3`. Denied attempts count too. Retries of a committed native run cannot create duplicate deliveries; run fencing and the session transaction decide whether a turn can commit.

`Knows` is conservative policy knowledge, not a claim that the secret sentence was literally disclosed. A budget-only output computed with a restricted reason still carries that component.

## Protocol

1. **Create:** trusted Board source ingestion creates public budgets ($8M, $3M, $5M), three restricted Nova reasons, and a public audit task. Only reasons get initial Carries. This is source ingestion, not a Board LLM computation over its entire history. Models cannot create or remove policy labels.
2. **Compute:** every artifact owned by or successfully delivered to the principal is supplied to the model. The runtime independently records DerivedFrom for the complete accessible set and derives output Carries. Earlier tool-generated messages within the same turn remain dependencies of later outputs. No wording-based tag removal occurs.
3. **Send:** the model calls the original `message_bot` tool. The runtime records the computed artifact and passes its body, routing/identity, and Carries to the receive gate. Sender Knows, Received, and dependency graphs do not travel.
4. **Evaluate:** under a per-session database row lock, combine the receiver's local facts with temporary Incoming and candidate Carries. Evaluate the executable stratified Datalog rules before writing any receiver payload.
5. **Allow:** add the artifact, Received, and transported Carries; derive Knows; write native sender and recipient receipts; queue a native recipient run. All state and chat writes commit together.
6. **Deny:** preserve the receiver's store exactly at the receive event. Do not write the candidate into the receiver's chat body or model inputs. Persist the attempted send and denied tool completion in the sender's chat. A separate generic failure notice may subsequently enter the receiver's store and wake it; that notice is a distinct event and contains no blocked body or restricted facts.
7. **Finish:** persist the final model reply and its snapshot, complete the native run/task, and publish realtime notifications. Cancelled, failed, timed-out, or stale-fence turns roll back message/store changes. Provider work may have already occurred even if the transaction rolls back.

A model computation has a 60-second timeout inside a 75-second transaction. Session locking prevents concurrent recipients from both accepting a third component against stale state. Native turns have a four-message tool-call cap. The application's automatic audit sends each request/reply/report once per intended recipient, and redundant wakeups complete without regenerating the same work. This is application scheduling, separate from Datalog Allow/Deny. Explicit user-directed turns can still attempt new sends, subject to the same receive gate.

## Rules

The executable AST is in `packages/core/src/policy/datalog.ts`. Its evaluator is finite, function-free, and stratified. These rules omit the diagnostic rule-name argument on Deny for readability:

```prolog
Carries(Y,P,C) :- DerivedFrom(Y,X), Carries(X,P,C).
Knows(A,P,C) :- Received(A,M), Carries(M,P,C).
New(A,M,P,C) :- Incoming(A,M), Carries(M,P,C), not Knows(A,P,C).

% R3a: three new components
Deny(A,M) :- New(A,M,P,C1), New(A,M,P,C2), New(A,M,P,C3),
             A != board, C1 != C2, C1 != C3, C2 != C3.
% R3b: two new components, one already known
Deny(A,M) :- New(A,M,P,C1), New(A,M,P,C2), Knows(A,P,C3),
             A != board, C1 != C2, C1 != C3, C2 != C3.
% R3c: one new component, two already known
Deny(A,M) :- New(A,M,P,C1), Knows(A,P,C2), Knows(A,P,C3),
             A != board, C1 != C2, C1 != C3, C2 != C3.
```

All three components must be distinct and from the same project. Board is receive-exempt. **There is no sanitization or declassification.**

## What to observe

Board distributes budgets and reasons. Auditor A asks all three departments for budgets through actual model tool calls. Department replies use their full local histories, so even budget-only replies inherit the restricted reason's component. The first two replies succeed; the third is rejected by R3c. Worker scheduling determines which department is third. Auditor A then sends an incomplete report to Board.

Open the third department's chat, find `message_bot → Auditor A · Denied (R3c)`, and click its dot. Auditor A's Before and After stores at that receive event are identical. Hover shows the attempted message's Carries and delivery ID. The generic failure notice is a later event; the denied body remains absent from Auditor A's inputs.

## Limits and validation

This is an App 2 messaging protocol, not a general policy for arbitrary computer tools. Native mobile does not yet expose the inspector; web and Electron share the chat implementation. Source initialization and runtime-created user/control notices are trusted ingestion paths. Generic delivery status is intentionally observable; timing/control-channel noninterference and LLM guessing are outside this version's guarantees.

Deterministic tests cover R3a/R3b/R3c, transitive propagation, duplicate labels, project separation, immutable snapshots, native peer receipts, worker tasks, denied payload exclusion, forbidden-tool rejection, and transaction rollback. Existing peer-message, thread-event, and pagination tests check compatibility. The browser test covers the original chat surface, hover tags, snapshot dots, mode switching, and narrow-screen layout. Live local OpenAI-compatible runs verify actual `message_bot` generation and receiver-side rejection.

The new migration adds message observation metadata and native workspace bindings. It does not rewrite original chats. The local Compose overlay must update **api, worker, and web** together.

### Store Inspector and Datalog Query

The native chat has a collapsible right-hand Store Inspector (an overlay on narrow
screens). Scope selects Global or a principal. Latest follows the current session;
a message's observation dot selects its event and actor. Before/After inspects the
persisted event snapshots, including denied deliveries whose receiver is unchanged.
Global shows the union of stored facts with owner annotations, not a new shared
agent store. Artifacts and denial witnesses remain available.

The read-only terminal accepts temporary ground facts, new predicates, safe rules,
positive recursion, stratified `not`, `!=`, anonymous `_`, and one `?-` query. Each
statement ends with a period. Uppercase identifiers are variables; double-quoted
strings support constants of any capitalization. Function terms, unsafe rules and
recursion through negation are rejected. Programs are limited to 20,000 characters,
100 rules, 10,000 derived facts and 500,000 evaluation operations. Limit errors
return no partial result. These limits apply only to observer queries.

Local queries use the real policy rules and selected local facts, together with
the temporary program. Global computes the real policy closure separately for
each principal before combining results; it never derives policy knowledge from
mixing stores. `Store_<Predicate>(Owner, ...)` relations preserve ownership.
Explicit user analysis rules can join across these relations. For example:

```prolog
Observed(A, P, C) :- Store_Knows(Owner, A, P, C).
?- Observed(A, P, C).
```

Query results retain their scope, event/revision, program and variable bindings in
panel history. Queries are authorized against the active user's native policy
session, reject stale revisions, and never persist facts or change live enforcement.
Incoming/New/Deny are receive-gate temporaries, not durable local-store relations;
users may introduce hypothetical Incoming facts in a local query to explore a gate.
