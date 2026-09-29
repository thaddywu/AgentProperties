# Executable Nova reasoning demo

This local demo follows **Distributed Policy Reasoning for Multi-Agent Systems**
(the current `main.tex`). It reuses Rakazo's UI components, theme, bot sidebar,
message layout, and right-side Store Inspector / Datalog terminal arrangement.
It runs an in-process messaging runtime with two auditors and does not require a
model, external service, database, or networked agents. It is a separate local
entrypoint; it does not replace the native worker's existing policy protocol.

## Run

On this workstation, all dependencies are already in the local `rakazo:policy-local`
image. The launcher mounts the current source into a fresh container:

```bash
cd ../rakazo-policy-clean
./scripts/nova-demo.sh
```

Open **http://127.0.0.1:5180/nova.html**. Stop with Ctrl-C. The demo state is in memory
and shared between tabs; restarting resets it. `NOVA_PORT` can change the host port;
`NOVA_IMAGE` can select another locally installed Rakazo development image.
The existing native app on port 5173 is unaffected.

With a supported Node version and workspace dependencies already installed, Docker
is optional:

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
- **Config** edits `Auditor`, `HasCap`, and `Requires` input facts. Removing A's
  capability changes the proof; granting B's capability changes feasible traces.
- The right-hand store separates configuration, runtime/trusted input, and derived
  closure. Every input includes ownership, origin, lifetime and runtime event ID.
  The scope selector filters the store display. The terminal explicitly queries
  the observer's global logical view of the selected snapshot.
- The event selector supports Before / After / Gate inputs. Denied deliveries
  retain their gate snapshot for proof inspection without storing temporary
  `Incoming` facts as persistent receiver knowledge.
- The terminal accepts safe, function-free Datalog: facts, new predicates, custom
  rules, variables, joins, recursion, stratified `not`, `!=`, `_`, and `?-` queries.
  Custom programs run on a copy. They cannot inject or override policy-derived
  predicates. Query limits produce errors rather than partial answers.
- **Why** returns a proof from evaluator provenance, including satisfied
  inequalities and negative checks, down to actual input facts.
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
?- Knows(auditor_a, nova, Part).
```

```prolog
PendingPart(M, Part) :- Incoming(A, M), Carries(M, nova, Part).
?- PendingPart(M, Part).
```

## Architecture and engine

The engine is the existing **Rakazo finite, function-free stratified Datalog
query evaluator**, `packages/core/src/policy/datalog.ts`. It computes a least
fixed point per stratum using rule joins and records the first supporting grounded
rule instance for each derived fact. The existing text parser and stratifier in
`query.ts` execute terminal programs. There is no separate JavaScript implementation
of IFC, capability denial, audit coverage, or completion.

| Module | Responsibility |
| --- | --- |
| `packages/core/src/policy/reasoning/policy.ts` | Executable rule AST, configuration, input validation; displayed rules are rendered from that AST |
| `runtime.ts` | Immutable snapshot copies, owned input records, send / pending / allow / deny transitions, actual event generation, preset scheduling |
| `analysis.ts` | Provenance traversal, copied-state what-if, event-subset enumeration, exhaustive progress-action search |
| `service.ts` | Browser-independent intent API, history selection, revision checks, configuration and witness replay |
| `apps/web/vite.nova.config.ts` | Local HTTP adapter for the runtime and analyses; works in development and preview |
| `apps/web/src/features/nova/` | Existing Rakazo primitives plus the facts inspector and five terminal tabs |

Only input records are persisted. `DependsOn`, `Carries`, `Knows`, `DenyReceive`,
`Audited`, and `Finished` are computed by the evaluator. Send runtime emits
`Sender` and `Before` from the sender's successful receive history, then creates
`Incoming`. The gate checks Datalog before recording `Receiver` and `Received`.
A denied payload stays outside the recipient's accessible messages. The observer
can inspect attempted payloads. Transported label snapshots come from `Carries`
at send time; they are not asserted as fresh source tags.

The store is an observer-level union emulating distributed state. Principal ownership
and carried labels remain explicit; this version does not claim that each agent
holds the complete union, or implement distributed networking. Audited facts describe
successful delivery for review, not a completed financial judgment.

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
   composer messages cannot supply `TrustedCarry`. HR has `hr_review` so it can
   receive its own tagged assignment. The `hr` principal produces the `hiring` part.
5. Search actions generate fresh message IDs when required and reuse the actual
   department/source lineage. Missing lineage is an error, never synthesized tags.
   Every recursive success must derive a previously missing `Audited` fact; no
   arbitrary depth bound is used. Search is exhaustive within the configured six-action domain.
6. Bodies are deterministic application text or user-entered text. The runtime and
   Datalog decisions are executable; no LLM generation is required for this offline demo.

## Validation

```bash
./scripts/nova-demo.sh test
./scripts/nova-demo.sh check
./scripts/nova-demo.sh build
```

Tests/build run in containers with `--network none`. The 40 unit/regression tests
cover all eight requested cases, support retraction, real provenance, configuration
changes, historical gate snapshots, stale revisions, prevented events, actual
completion replay, and existing query/protocol behavior. Type checking and the
production build also pass.

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
