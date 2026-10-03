# Executable Nova reasoning demo

This local demo follows **Distributed Policy Reasoning for Multi-Agent Systems**
([research/main.tex](research/main.tex)). It reuses Rakazo's UI components, theme, bot sidebar,
message layout, and right-side Store Inspector / Datalog terminal arrangement.
It runs an in-process messaging runtime with two auditors and does not require a
model, external service, database, or networked agents. It is a separate local
entrypoint; it does not replace the native worker's existing policy protocol.

## Run

Build the pinned Soufflé 2.5 image once, using the existing `rakazo:policy-local`
image as its base. Setup downloads the official Linux x86_64 release and verifies
its SHA-512 checksum. The launcher mounts the current source:

```bash
./nova-demo.sh setup  # once; requires network
./nova-demo.sh
```

Open **http://127.0.0.1:5180/** (redirects to `/nova.html`). The root launcher defaults
to **restart**: it replaces the previous container, starts the frontend and policy
worker in the background, checks the page/API and executes a Datalog query. It
prints progress, saved-state counts, recent logs and the URL. Closing the terminal
does not stop the demo. Use `./nova-demo.sh status`, `./nova-demo.sh logs`, or
`./nova-demo.sh stop` to inspect or stop it. `serve` starts it and follows logs;
Ctrl-C stops following logs, while the container keeps running. If the browser
reports a timeout, check the port forward and run `./nova-demo.sh` again.

The runtime is shared
between tabs and checkpointed in the Docker volume `nova-reasoning-state`; restarting
preserves it. Use **New**, **Earlier**, or **Denial** for an explicit reset.
`NOVA_PORT` changes the host port; `NOVA_CONTAINER` and `NOVA_STATE_VOLUME` allow
an isolated second instance. `NOVA_IMAGE` selects an image with Soufflé and Rakazo installed.
The existing native app on port 5173 is unaffected.

With a supported Node version, workspace dependencies, Soufflé 2.5 and Linux
`prlimit` installed, Docker is optional (set `NOVA_STATE_FILE` to persist state):

```bash
cd apps/web
node_modules/.bin/vite --config vite.nova.config.ts
```

The same configuration supports `vite build --config vite.nova.config.ts` and
`vite preview --config vite.nova.config.ts`. Preview includes the local runtime API;
serving the compiled HTML alone is insufficient.

## Use

- **New → Next event** executes the episode one send / receive at a time.
  **Earlier** runs through Procurement's delivery to A; **Denial** runs through
  the pending Hiring delivery to A. These presets call runtime methods; they do
  not load precomputed event records or outcomes.
- The composer sends a real in-process message. Its source tags are inherited
  from the sender's receive history by Datalog. **Check & deliver** executes the
  current policy gate and either commits the receive or blocks it.
- **Config** edits `Auditor`, `HasCap`, `Requires`, `TagGroup`, and `AuditGoal` input facts. Removing A's
  capability changes the proof; granting B's capability changes feasible traces.
- The right-hand store separates configuration, runtime/trusted input, and derived
  closure. Every input includes ownership, origin, lifetime and runtime event ID.
  The scope selector chooses an actual local store for both Terminal and Why.
  The default is Auditor A. **Debug · reconstruct all local stores** explicitly
  requests a transient union of independently computed local closures.
- The event selector supports Before / After / Gate inputs. Denied deliveries
  retain their gate snapshot for proof inspection without storing temporary
  `Incoming` facts as persistent receiver knowledge.
- The terminal accepts safe, function-free Datalog: facts, new predicates, custom
  rules, variables, joins, recursion, stratified `not`, `!=`, `_`, and `?-` queries.
  Custom programs query a copy of the computed store, with temporary facts and
  custom relations. They cannot inject or override policy-derived predicates.
  Use What-if to recompute policy after editing input facts. Query limits produce
  errors rather than partial answers.
- **Why** renders Soufflé's native JSON provenance down to runtime input facts.
  It returns one minimum-height local derivation tree, not every possible proof.
  Received protocol facts are explicit leaves; the UI does not fabricate a remote
  proof or fetch another agent's private history. Native
  optimized rules and checks are preserved; comparison leaves may show internal
  symbol IDs, and eliminated empty-relation checks may be omitted by Soufflé.
- **What-if** edits REMOVE / ADD / QUERY and displays changed derived facts.
- **Prevention** accepts named event bundles, enumerates subsets in increasing
  cardinality, and returns every minimum solution. The editable universe is capped
  at 12 events to bound the explicitly exponential analysis.
- **Speculative** accepts the goal and an editable subset of the six configured
  department-to-auditor actions. Its default basis is an explicitly labelled,
  separately executed earlier runtime; choose **Selected runtime snapshot** to
  analyze current configuration/history instead. Settle pending receives first.
  Every hypothetical edge uses the same send and receive methods as normal
  execution. The search classifies every immediate edge and returns a real witness.
  **Replay completion in runtime** replaces the demo state with that starting
  state plus the trace, executing every receive gate again. Stale witnesses cannot
  be replayed until analysis is rerun.

Examples for Terminal:

```prolog
?- Knows(auditor_a, Tag).
```

```prolog
PendingTag(M, Tag) :- Incoming(A, M), Propagated(M, Tag).
?- PendingTag(M, Tag).
```

## Architecture and engine

Nova uses the official **Soufflé 2.5** binary in interpreted mode. `policy.ts`
remains the single rule AST source; `souffle.ts` serializes it as typed `.decl`
relations and native rules, supplies one principal's actual local inputs including its own configuration replicas, and reads
native relation output. The Rules panel displays this generated executable Soufflé program.
The terminal retains the existing safe syntax parser (`not`, `?-`, unquoted
lowercase constants), translates parsed AST into Soufflé, and delegates evaluation
to the native engine. It accepts the documented subset, not arbitrary Soufflé
file directives or external functors. The older app's evaluator remains unchanged;
Nova no longer invokes it.

Why invokes `souffle -t explain`, requests JSON output, and adapts the returned
native tree to the existing UI. What-if and minimum prevention recompute independent local stores on edited copies;
speculative search uses the actual local send/gate/summary protocol for each edge; Soufflé
provenance alone does not implement these analyses. A bounded cache reuses only
identical program/input evaluations. See the [official provenance documentation](https://souffle-lang.github.io/provenance).

Evaluation runs in a separate child process, outside Vite's HTTP event loop.
Native calls have CPU, memory, output and wall-time limits. A whole analysis has a
20-second deadline; timeout kills the worker process group and the next request
restores the last committed checkpoint. Concurrent API operations receive a clear
busy error; page serving stays responsive. The browser also times out requests.
Changes are committed only after a successful request; failed operations roll back.

| Module | Responsibility |
| --- | --- |
| `packages/core/src/policy/reasoning/config.ts` | Default editable configuration facts |
| `policy.ts` | Executable rule AST and input schemas; displayed rules are rendered from that AST |
| `protocol.ts` | Global replication, local tuple patterns, restricted locations and explicit transfer definitions |
| `local-store.ts` | Local input selection, location-bound rules, independent native evaluations and observer union |
| `runtime.ts` | Immutable snapshot copies, owned input records, send / pending / allow / deny transitions, actual event generation, preset scheduling |
| `souffle.ts` | Native program serialization, subprocess limits, tuple output and native JSON proof adaptation |
| `analysis.ts` | Native explanation requests, copied-state what-if, event-subset enumeration, exhaustive progress-action search |
| `service-process.ts`, `service-worker.ts` | HTTP/compute isolation, deadline recovery, transactional checkpoints |
| `service.ts` | Browser-independent intent API, history selection, revision checks, configuration and witness replay |
| `apps/web/vite.nova.config.ts` | Local HTTP adapter for the runtime and analyses; works in development and preview |
| `apps/web/src/features/nova/` | Existing Rakazo primitives plus the facts inspector and five terminal tabs |

Only input records are persisted. `DependsOn`, `Propagated`, `Knows`, `DenyReceive`,
`Audited`, and `Finished` are computed by the evaluator. Send runtime emits
`Sender` and `Before` from the sender's successful receive history, then creates
`Incoming`. The gate checks Datalog before recording `Receiver` and `Received`.
A denied payload stays outside the recipient's accessible messages. The observer
can inspect attempted payloads. Transported label snapshots come from `Propagated`
at send time; they are not asserted as fresh source tags.

Only `stores[principal]` is authoritative and persisted; there is no top-level fact
store or global partition. Historical snapshots are also maps of local stores.
Configuration predicates listed in `PROTOCOL.replicated` are explicitly copied to
every principal at initialization and configuration updates. Evaluation reads those
local copies; it does not fetch configuration from a global table.
There is no cross-store policy join. `PROTOCOL.local.Knows = ["@self", "_"]`
means `Knows(A, _)` belongs to store A. `localRules()` binds the corresponding
head variable to A before passing rules to Soufflé; it is not a display filter.
`closure(owner)` requires a principal. `reconstructDebugView()` assembles an observer
union on demand, after independent local evaluations, without re-running policy
on the union. Debug Terminal queries can join that temporary result. Each request
reconstructs it from current local inputs (or selected historical partitions).
The API's `records` list is a transient inspector projection, never checkpointed.
Local Terminal and Why requests never access other principals' stores.

The message route exports the sender's locally derived `Propagated(M, Tag)`
and imports `TransportTag(M, Tag)` into the receiver's gate store. Datalog
then derives local `Propagated` from the received metadata. Imported labels are
temporary while pending, retained on allow, and discarded on deny. Only Board's
trusted ingestion creates `TrustedSource`; other principals receive transported
labels, not permission to create source tags.

After an allowed receive, an auditor exports its locally derived `Audited` facts
as `AuditReceipt(A, Tag)` to Board. Board derives audit coverage and
`Finished` from those receipts; it does not import auditors' `Knows`. Receipt
transfer is synchronous and application-trusted. Receive-triggered transfers are
recorded in the receive event. Configuration updates also publish newly enabled
local audit results, so Board does not wait indefinitely for another receive.
A receive gate verifies that all tags in the message envelope are present locally;
an incomplete envelope or missing local receive intent causes an error before any delivery mutation. Audited means delivery for review, not a financial
judgment. This version does not implement separate network processes or signatures.

Protocol copies are independent inputs after transmission. Removing a sender's
source fact does not revoke an already delivered label or receipt. What-if edits
only the specified records; event prevention removes exactly its configured
bundle. For a counterfactual that also retracts a sent receipt/label, explicitly
include that protocol record. Automatic retraction requires an additional protocol.

Old checkpoints are upgraded using their recorded message labels and successful
receive history, including before/after snapshots; message IDs, event ordering and
revision are preserved. The upgrade does not derive new tags from a global join.

## Opaque tags and grouped exposure

Taint facts use one opaque tag: `TrustedSource(M, Tag)`, `Propagated(M, Tag)`,
`TransportTag(M, Tag)` and `Knows(A, Tag)`. Capability requirements use
`Requires(Tag, Cap)`; audit summaries use `Audited(Tag)` and `AuditReceipt(A, Tag)`.
The engine never splits tag strings. Default names are `nova_procurement`,
`nova_facility` and `nova_hiring`.

`TagGroup(Tag, Group)` is replicated configuration that preserves the original
same-project exposure rule. The three-tag denial requires three distinct tags
with a common group. Tags from unrelated groups do not combine into a violation;
unregistered tags do not participate in this grouped constraint. Capability rules
still apply independently. `AuditGoal(Group, T1, T2, T3)` configures which three
tags complete `Finished(Group)` for this demo. Neither concept is embedded in
propagation tuples. Config editing supports both new predicates.

The checkpoint migration renames old predicates and replaces `(Proj, Part)` with
a tag in input facts, message labels and event snapshots. It also supplies group
and goal configuration to preserve previous decisions; restarting keeps the episode.

## Small specification adjustments

1. The TeX's third-part rule covers one incoming part plus two known parts. Two
   additional Datalog rules cover a multi-label incoming message (two incoming +
   one known, or three incoming), preserving the intended exposure policy.
2. A delivery is two transitions: send creates a pending `Incoming`; settlement
   evaluates current state and removes it. After rejection, the denial proof remains
   available through the recorded gate snapshot, not as persistent knowledge.
3. `Receiver` and `Received` are emitted together only on successful delivery and
   belong to the same preventable event. `Before` is recorded only for messages
   received before a subsequent send. No declared episode facts stand in for these
   runtime events.
4. Board assignments are trusted ingestion, tagged by the application. Ordinary
   composer messages cannot supply `TrustedSource`. HR has `hr_review` so it can
   receive its own tagged assignment. The `hr` principal produces the `hiring` part.
5. Search actions generate fresh message IDs when required and reuse the actual
   department/source lineage. Missing lineage is an error, never synthesized tags.
   Every recursive success must derive a previously missing `Audited` fact; no
   arbitrary depth bound is used. Search is exhaustive within the configured six-action domain.
6. Bodies are deterministic application text or user-entered text. The runtime and
   Datalog decisions are executable; no LLM generation is required for this offline demo.

## Distributed completeness checks

`distributed-conformance.test.ts` explores 96 scenarios: all six department reply
orders, all eight auditor-routing combinations, with and without B's HR capability.
At 1,248 initial/send/receive checkpoints it compares every derived tuple in the
reconstructed local closures with a centralized Soufflé evaluation used only as a
test oracle. It also checks the actual allow/deny decision at every gate.

Additional tests cover interleaved pending messages, recursive multi-tag forwarding,
configuration-triggered audit summaries, serialization, independent configuration
copies, historical migration and fresh debug reconstruction. Fault-injection tests
drop a transport tag or audit receipt and demonstrate the expected missing facts;
a debug query must not conceal those omissions by globally re-running policy.
Local query/proof isolation is tested with another store made inaccessible.
These are checks of the current protocol and rule set, not a proof for arbitrary
new policy rules or asynchronous network failures.

## Validation

```bash
./scripts/nova-demo.sh test
./scripts/nova-demo.sh check
./scripts/nova-demo.sh build
```

Tests/build run in containers with `--network none`. The 162 unit/regression tests
cover all eight requested cases, support retraction, real provenance, configuration
changes, historical gate snapshots, stale revisions, prevented events, actual
completion replay, and existing query/protocol behavior. Type checking and the
production build also pass. Native adapter tests cover minimum-height proofs,
quoted symbols, nullary queries, anonymous variables, unsafe rules and directive rejection.
Local-store tests additionally cover isolation, missing envelope metadata, configurable
location patterns, temporary labels, Board receipts, independent copies and checkpoint migration.

With the demo running and Playwright/Chromium installed:

```bash
node scripts/nova-browser-test.mjs
```

The browser suite verifies variable queries, proof trees, editable what-if and event
sets, derived-write rejection, speculative classification, runtime witness replay,
stepwise sends/receives, Before/After queries, config edits, and narrow-screen composer
and inspector behavior. It saves screenshots to `/tmp/nova-browser-review` by default
(`NOVA_SCREENSHOTS` overrides this). `NOVA_URL`, `NOVA_CHROMIUM`, and
`NOVA_PLAYWRIGHT_MODULE` support an existing local browser installation.
