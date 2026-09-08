# Claude handoff — implement the frozen Base App

Copy everything below this line into a fresh Claude coding session whose
working directory is `/home/thaddywu/Agent`.

---

You are implementing version 1 of the Multi-Supplier Replenishment Automation
Base App for a single urban convenience store.

Work autonomously until the complete local application and its tests are
finished. Do not stop after scaffolding, a partial vertical slice, or a plan.

## Working directory and authoritative requirements

Your repository working directory is:

```text
/home/thaddywu/Agent
```

The only functional requirements for this implementation are these two frozen,
read-only documents:

```text
apps/multi-supplier-replenishment/v1/app-spec-v1.md
apps/multi-supplier-replenishment/v1/policy-v1.md
```

Before writing code, read both documents completely. Verify their exact
SHA-256 values:

```text
app-spec-v1.md
8d4c4b3cc3d57d8d457a76f7057d5e9a8996401587e99550b3bde728d3634a98

policy-v1.md
6381653ecf275dfd5f537ce6fd71644deb782e185daead265ab989c2e0ba3966
```

If either hash differs, stop and report the mismatch before implementing.

Treat the specification and policy as frozen. Do not edit them, reinterpret
them to make implementation easier, or silently weaken a requirement. If you
find a genuine contradiction that prevents implementation, stop and report the
exact conflicting sections. Do not guess around it.

Do not use the first case study, another application implementation, or any
repository-level runtime/integration/evaluation code as a template or source of
functional behavior. Build this application independently from the two frozen
documents. Do not inspect unrelated application directories unless needed to
obey repository-wide operating instructions automatically supplied to you.

## Output boundary

Create the complete implementation only inside this new isolated directory:

```text
apps/multi-supplier-replenishment/v1/base-app/
```

The directory does not yet exist. If it already exists or contains files when
you begin, stop and report that fact rather than overwriting it.

Do not modify anything outside `base-app/`. In particular, do not change the
frozen spec, frozen policy, design history, the first case study, or any shared
repository code.

## Independence requirements

This must be a normal, independently useful replenishment application.

- Implement only behavior justified by the frozen specification and policy.
- Do not add hidden checks, extra restrictions, instrumentation, wrappers,
  model interpreters, or infrastructure for a possible later research system.
- Do not optimize class names, method signatures, module boundaries, or call
  paths for hypothetical future integration.
- Do not import or depend on repository code outside `base-app/`.
- Do not use an LLM, agent framework, hosted service, real supplier account,
  cloud database, or network call.
- All external systems must be represented by explicit interfaces and fully
  local deterministic implementations.
- The application database and mock external world state must remain distinct.

The application must implement the policy as ordinary application behavior
because that policy is one of its frozen requirements. Do not add requirements
beyond it merely because they sound safer.

## Required deliverable

Build a complete Python 3.11+ project containing at least:

1. A clear installable application package.
2. A SQLite persistence layer for application-owned state.
3. Explicit interfaces for:
   - clock;
   - Inventory Ledger;
   - POS Sales History;
   - Calendar/Holiday Service;
   - Supplier A; and
   - Supplier B.
4. Deterministic local/mock implementations of every external service.
5. Persistent mock world state and fixtures separate from the application
   SQLite database.
6. The exact deterministic forecast, replenishment, supplier-selection,
   outstanding-order, and unknown-outcome behavior in the frozen documents.
7. A long-running daily scheduler plus a manual-run command.
8. Human-readable and JSON inspection commands for runs, SKU decisions,
   purchase attempts, reconciliation history, and recorded supplier orders.
9. Complete deterministic tests.
10. A README with setup, run, test, fixture, scheduler, and inspection examples.
11. An `IMPLEMENTATION-NOTES.md` mapping specification sections to modules and
    listing intentionally unspecified coding choices you made.

Choose sensible package and module names yourself. Keep the design compact and
maintainable. Do not create microservices or unnecessary abstraction layers.
Prefer the Python standard library for runtime behavior; declare every required
dependency in `pyproject.toml`.

## Behavioral requirements that must not be reduced to stubs

Implement the full normal workflow, not placeholder methods such as “forecast
demand” or “select supplier.” In particular:

- Use Decimal arithmetic and the exact 28-day calendar-normalized exponential
  smoothing equations.
- Apply future calendar multipliers and ceiling only after aggregating the
  future daily forecasts.
- Compute supplier-specific coverage horizons from lead time, the one-day
  review period, and safety days.
- Compute order-up-to targets, inventory position, raw requirements, and pack
  rounding exactly.
- Obtain complete supplier-order state and matching Inventory Ledger receipts
  before calculating outstanding quantity.
- Count accepted, shipped, and delivered-but-unreceived orders correctly,
  including orders created outside this application.
- Build feasible candidates from actual offer identity, price, pack size,
  availability, lead time, owner limits, and hard inventory exposure.
- Apply the exact two ranking paths for candidates that avoid projected
  stockout and candidates that do not.
- Persist the purchase attempt before calling `place_order`.
- Pass the actual selected supplier SKU, quantity, expected unit price,
  destination, and stable idempotency key.
- Validate every accepted response field.
- Treat timeouts, lost responses, interrupted dispatch, and contradictory
  accepted responses as unknown outcomes.
- Reconcile unknown outcomes by idempotency key before planning and never
  blindly retry or switch suppliers.
- Enforce the one-worker, one-completed-scheduled-run-per-date semantics.
- Keep all failure, skip, escalation, and unknown outcomes visible to the
  operator.

Do not put implementation shortcuts into mocks that make core behavior
untestable. The mocks must be authoritative services with their own state and
must record raw supplier calls and resulting supplier-world orders.

## Local world and example fixtures

Provide committed example configuration and world-state fixtures that make the
application demonstrable offline. Include enough configured SKUs to show, in
one or more deterministic scenarios:

- a normal accepted replenishment order;
- no order needed;
- Supplier A unavailable while Supplier B is usable;
- an owner-limit escalation;
- an existing manual or external outstanding order;
- a delivered order awaiting an Inventory Ledger receipt;
- a definitive supplier rejection; and
- a timeout/unknown outcome followed by reconciliation.

Fixtures must not hide state inside the application database. A user must be
able to inspect the external world files and the supplier raw-call log.

## Testing requirements

Implement every test category in Section 16 of the frozen specification. The
suite must cover normal workflows, boundary values, malformed data, missing
data, lifecycle transitions, deterministic tie-breaking, restart/idempotency,
and unknown-outcome recovery.

For every test involving a possible purchase, assert all of the following:

- resulting application decision;
- exact raw supplier call count;
- exact raw supplier call arguments;
- authoritative supplier-world order state;
- relevant Inventory Ledger world state; and
- durable application journal state.

Tests must not contact a network or depend on wall-clock time, machine locale,
test ordering, or random identifiers. Inject time. Make generated IDs stable
and reproducible where the frozen documents require deterministic behavior.

Add focused calculation tests with independently stated expected Decimal and
integer results; do not test the forecast merely by recomputing it through the
same production helper.

## README and usability requirements

The README must let a new developer, from the `base-app/` directory:

- create/install a development environment;
- run the full tests;
- initialize a fresh local app database and mock world;
- run one manual replenishment cycle;
- start the scheduler without contacting external services;
- inspect runs, SKU decisions, attempts, orders, and raw supplier calls;
- reproduce an unknown outcome and then reconcile it; and
- reset or copy example state without deleting anything outside `base-app/`.

Document what belongs to the application database versus the mock external
world. Clearly identify the consequential supplier `place_order` methods and
their actual argument representation, but do not add integration hooks around
them.

## Completion procedure

Before declaring completion:

1. Run the entire test suite from a clean command documented in the README.
2. Run at least one end-to-end example using the committed local fixtures.
3. Confirm no file outside `base-app/` was modified.
4. Search for TODOs, placeholders, skipped tests, accidental network calls, and
   imports from outside `base-app/`; remove them or report a genuine blocker.
5. Confirm the frozen requirement files still have the exact hashes above.

In your final response, provide:

- a concise architecture summary;
- files and directories created;
- exact setup, test, and demo commands;
- test counts and results;
- exact supplier `place_order` implementations and their call paths;
- any intentionally unspecified coding choices you made; and
- any genuine discrepancy or unimplemented requirement.

Do not claim completion if tests are failing or a frozen requirement is not
implemented. Do not edit the frozen documents to make the implementation pass.
