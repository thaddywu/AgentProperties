# Three-application pipeline experiment

Completed 2026-11-13. The existing recommended cohort supplied LabCluster,
Payments and Multi-agent. All three completed the same five Python module
interfaces without application names or predicates in the generic analysis code.

| Application | Application tests | Gate decisions replayed exactly | Captured trajectories | NL QA questions | Viewer sentences opened |
| --- | ---: | ---: | ---: | ---: | ---: |
| LabCluster | 16 | 241 | 16 | 4 | 44 |
| Payments | 17 | 31 | 17 | 5 | 33 |
| Multi-agent | 16 | 172 | 16 | 4 | 24 |
| Total | 49 | 444 | 49 | 13 | 101 |

All application tests passed, with no skipped tests. All completed gate decisions
replayed consistently, with no missing gate decisions. Browser checks were
headless and reported no page errors. The framework's 96 deterministic offline
tests and three existing browser journeys also passed.

## What ran

1. Fresh coding-model sessions inspected each clean source checkout, generated
   rules and additive hooks, ran real native-engine checks, and repaired failures.
2. Separate reverse sessions received frozen implementation/framework evidence,
   excluding the original policy, forward plan and generated tests. Structural
   rule coverage and exact implementation citations were checked.
3. A separate alignment pass matched source sentences to those frozen readings.
   Each published viewer bundle was validated and every source sentence opened
   in the shared review UI. No human ratings were fabricated.
4. Publication checks ran the original callbacks in isolated, network-disabled
   containers, without policy-authoring documents. External SDKs, remote models
   and transports used explicit offline fixtures. The policy runtime and native
   Soufflé evaluator were real. Original source checkouts stayed clean.
5. The unified `policyscope pipeline --reuse-port` command consumed these newly
   generated, fixed artifacts, reran publication checks, replayed all captured
   decisions, and asked three generic NL questions per application. Additional
   questions retrieved captured input facts for each app and explained an
   uncertain Payments execution. Model responses retained deterministic results
   and validated event references.

The table counts one final publication check per application and successful QA
questions. Intermediate failures and repairs remain in private evidence. These
are development checks written during adaptation, rather than held-out tests or
an independent proof that the original policies were translated correctly.

## Outcomes and policy coverage

The 444 captured calls comprise 370 adapter-reported `applied`, 65 `blocked`, eight
`not_applied`, and one `unknown`. Every blocked call records an uninvoked callback.
The uncertain call's permission replayed successfully, while its business outcome
and rollback stayed unknown. A successful decision replay certifies agreement
with captured rules/facts, not successful business execution.

**Full original-policy enforcement is not established for any of the three apps.**
Concrete limits remain visible in the generated manifests and reverse readings:

- **LabCluster:** actor labels require trusted host binding; text isolation uses
  observed literal matching and cannot guarantee semantic information-flow
  isolation. Priority depends on existing counters/configuration. Multiple
  processes and asynchronous external stop confirmations are outside the local
  simulator's guarantees.
- **Payments:** the original app lacks authoritative exact-request user
  confirmation, identity-verification/cooling-off and transfer-linked provenance
  producers. Tests expose successful unconfirmed transfers as known gaps. Role
  gates and local daily-limit checks execute, while P1/P2 and end-to-end P4/P6
  coverage remain incomplete. Unauthenticated endpoints and remote channels need
  additional integration.
- **Multi-agent:** budget reservations and information-flow/history gates execute,
  but actual cloud cost arrives after the provider call; overspending can be
  detected after spending rather than fully prevented. MCP/A2A context requires
  trusted identity binding. Tests use a single-process replica with offline
  provider/transport fixtures and do not establish real protocol integration or
  cross-process consistency.

These gaps belong to the application integration and policy fidelity boundary.
The shared trajectory interface makes them inspectable; it does not create
missing authority, observations or completion evidence.

## Reuse and evidence

See the [trajectory contract](../trajectory.md) for API requirements and executable
commands. New apps supply their own predicates and authoritative adapters; they
reuse the same capture, replay, query and QA implementation. Raw chat logs require
a trusted converter with exact policy identity and decision-time fact snapshots.

The [aggregate JSON](three-app-pipeline.json) contains public measurements. Full
source copies, generated ports, execution reports, frozen readings, alignments,
QA prompts/results, provider usage and browser screenshots remain in private
run storage outside the checkout. No connection settings or raw trajectories are
published here.
