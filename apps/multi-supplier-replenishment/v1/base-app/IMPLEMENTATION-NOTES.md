# Implementation notes

This maps the frozen specification and policy onto the modules of this
application, then lists the coding choices the frozen documents deliberately
left open.

Authoritative requirements:

* `../app-spec-v1.md` — SHA-256 `8d4c4b3cc3d57d8d457a76f7057d5e9a8996401587e99550b3bde728d3634a98`
* `../policy-v1.md` — SHA-256 `6381653ecf275dfd5f537ce6fd71644deb782e185daead265ab989c2e0ba3966`

---

## 1. Specification sections to modules

| Spec section | Module(s) | Notes |
|---|---|---|
| 3. Time, units, currency, arithmetic | `timeutil.py`, `decimals.py` | RFC 3339 UTC persistence, store-time-zone business dates, a 28-digit decimal context, two-decimal money |
| 4. External service boundaries | `interfaces.py`, `domain.py` | Protocols and the value types they exchange |
| 4.1 Clock | `adapters/clock.py` | `SystemClock`, injectable `FixedClock` |
| 4.2 Inventory Ledger | `adapters/inventory.py`, `engine.ReplenishmentEngine._inventory_snapshot`, `engine._inventory_record` | Snapshot-level usability is fatal to the run; record-level problems block one SKU |
| 4.3 POS Sales History | `adapters/sales.py`, `engine._sales` | Exactly 28 records, one per date; a missing date is never a zero |
| 4.4 Calendar/Holiday Service | `adapters/calendar.py`, `engine._calendar` | History plus every future date inside the maximum coverage horizon |
| 4.5 Supplier services | `adapters/supplier.py` | Offers, complete order snapshots, idempotency lookup, and the one `place_order` effect |
| 5.1 Data ownership | `journal.py`, `README.md` | Journal rows record observations, never authority |
| 5.2 SKU configuration | `config.SkuConfig` | |
| 5.3 Purchase order | `domain.PurchaseOrder` | |
| 5.4 Outstanding quantity | `outstanding.py` | Lifecycle contributions, receipt matching, and inconsistency blocking |
| 5.5 Run record | `journal.RunRecord`, `storage.py` | `RUN-000001`, one scheduled run per local business date |
| 5.6 SKU decision record | `engine.SkuResult`, `journal.record_decision` | All material inputs and derived values are stored as JSON |
| 5.7 Purchase attempt | `journal.commit_attempt`, `execution.py` | Committed before any supplier call |
| 6. Forecasting model | `forecast.py` | Normalization, exponential smoothing, aggregate then single ceiling |
| 7.1 Review period and horizon | `planning.coverage_days`, `planning.coverage_window` | `L + 1 + S`, first covered date is the run date |
| 7.2 Order-up-to target | `planning.build_plan` | Target, position, raw requirement, pack rounding |
| 7.3 Inventory exposure | `planning.SupplierPlan.exposure_after_order`, `engine._process_sku`, `selection.owner_limit_failures` | The pre-offer hard-maximum check lives in `_process_sku` |
| 7.4 Projected stock before arrival | `planning.project_stockout` | Ranking only; never alters authoritative quantities |
| 8. Feasibility and selection | `selection.py`, `engine._decide` | Usability checks, owner limits, and the two ranking paths |
| 9. Purchase execution | `execution.py` | Key format, single call, full response validation |
| 10. Unknown-outcome reconciliation | `reconciliation.py` | Stable attempt-ID order, before any planning input |
| 11. Scheduling and orchestration | `scheduler.py`, `engine.execute`, `locking.py` | Daily time, catch-up, no repeat, no overlap |
| 12. Failure handling | `engine.py`, `execution.py`, `reconciliation.py` | Each listed failure has its own journalled outcome |
| 13. Configuration | `config.py`, `adapters/registry.py` | Whole-file rejection; adapters must construct |
| 14. Inspection interface | `reporting.py`, `cli.py` | JSON and text for every required view |
| 15. Persistence and restart | `storage.py`, `journal.py`, `app.py` | Explicit schema creation, `recover_interrupted` on startup |
| 16. Testing | `tests/` | See section 3 below |
| 17. Boundaries and non-goals | — | Nothing outside the version-1 contract is implemented |

### Policy sections to code

| Policy section | Where it is enforced |
|---|---|
| 4. Task boundary | Only `place_order` mutates anything external; no other supplier mutation exists on the interface |
| 5. Required state before planning | `engine._inventory_record`, `engine._sales`, `engine._calendar`, `outstanding.compute_outstanding` |
| 6. Outstanding-order interpretation | `outstanding.compute_outstanding`, `outstanding._receipt_problems` |
| 7. Forecasting and replenishment duties | `forecast.py`, `planning.py` |
| 8. Supplier and offer conditions | `selection.check_offer_usable` |
| 9. Quantity and exposure | `planning.build_plan`, `selection.owner_limit_failures`, `engine._process_sku` |
| 10. Price, spend, lead time | `selection.owner_limit_failures`, `engine._decide` |
| 11. Selection and order scope | `selection.rank_candidates`, one attempt row per `(run_id, sku)` |
| 12. Purchase submission | `journal.commit_attempt`, `execution.place_purchase_order` |
| 13. Order outcomes and retries | `execution.py`, `reconciliation.py` |
| 14. Failure and uncertainty | `engine.py` per-SKU and run-level outcomes |
| 15. Escalation | `DecisionOutcome.ESCALATION_REQUIRED`; no operation converts one into a purchase |
| 16. Configuration integrity | `config.py`; nothing writes the configuration file |
| 17. Scheduling and duplicate prevention | `scheduler.py`, the partial unique index on scheduled runs |
| 18. Records and accountability | `journal.py`, `reporting.py` |

---

## 2. Intentionally unspecified choices

These were not fixed by the frozen documents. Each is a coding decision made
here, with the reasoning.

### Naming and layout

1. **Package name `replenishment`, `src/` layout, module split as listed
   above.** The specification says to choose sensible names. Modules follow the
   specification's own sections so a reader can move between the two.
2. **Command name `replenish`**, with subcommands `init-db`, `init-world`,
   `run`, `scheduler`, `status`, `runs`, `show-run`, `decisions`, `attempts`,
   `orders`, and `supplier-calls`. Every one accepts `--json`.
3. **CLI exit codes**: `0` for success, including a run that completes with
   exceptions; `1` for a `FAILED` run; `2` for a configuration error, a lock
   rejection, or an unknown run ID.

### Data model details

4. **An additional decision outcome, `ORDER_OUTCOME_UNKNOWN`.** Section 5.6
   lists the outcomes an implementation must include "at least".
   `BLOCKED_UNKNOWN_ATTEMPT` describes a SKU that *this* run refused to plan
   because an *earlier* attempt is unresolved. An attempt that becomes unknown
   *during* this run is a different operator-visible fact, and policy section
   14 forbids silently converting one state into another, so it has its own
   outcome. Both are exception outcomes for the run status.
5. **`InventorySnapshot.malformed`.** Section 4.2 requires a malformed ledger
   record to be unusable for its own SKU while other SKUs continue, and policy
   section 14 requires "missing" and "malformed" to stay distinguishable. A
   record whose fields cannot be decoded at all cannot be expressed as an
   `InventoryRecord`, so the adapter reports it in this separate tuple and the
   engine turns it into a `DATA_ERROR` naming the decoding problem. Records
   that are decodable but wrong — negative, inactive, wrong unit, duplicated —
   travel as ordinary records and are rejected by the engine.
6. **`PurchaseOrder.store_sku` is filled in by the application.** Section 5.3
   lists a mapped store SKU on the purchase order, but `place_order` never
   sends one and a supplier has no notion of store SKU identity. Adapters
   therefore leave it `None` and the application resolves it through the
   owner's supplier mapping (`Config.supplier_sku_index`).
7. **Money is stored as decimal text and timestamps as RFC 3339 UTC text** in
   SQLite. Binary floating point never touches a price or a forecast.
8. **Run IDs** are `RUN-%06d` from one monotonic sequence shared by scheduled
   and manual runs, so identities are stable, ordered, and distinct.
9. **One scheduled run per local business date** is enforced by a partial
   unique index (`ux_runs_scheduled_business_date`), not only by application
   logic.
10. **`purchase_attempts` carries a unique `(run_id, sku)` constraint** in
    addition to the unique idempotency key, which is how "at most one purchase
    order for one store SKU in one run" is made structural.

### Arithmetic

11. **A dedicated decimal context of 28 digits with `ROUND_HALF_EVEN`**
    (`decimals.FORECAST_CONTEXT`). Section 3 requires "at least 28 significant
    digits"; 28 is the smallest conforming choice and keeps results
    reproducible across machines. All forecast arithmetic runs inside this
    context; nothing is rounded until the single ceiling.
12. **Base demand is journalled exactly as computed**, so an exact zero can
    print as `0E-52`. Normalizing it for display would mean rounding a value
    the specification says must not be rounded.
13. **Offer unit prices must carry exactly two decimals**, matching the
    two-decimal rule for money in section 3. An offer priced `1.001` is
    unusable rather than silently rounded.

### Decision precedence and horizons

14. **Owner lead-time limits are checked before the plan is built.** An offer
    whose lead time exceeds `max_lead_time_days` can never be executable, so
    building its coverage horizon is pointless — and doing so would demand
    calendar labels beyond the horizon the run requested. The calendar range
    a run asks for is therefore exactly
    `[run_date - 28, run_date + max_lead_time_days + safety_days]`.
15. **Outcome precedence when nothing is executable**, in order:
    (a) a candidate with a positive requirement that failed only an owner
    price, spend, or exposure limit gives `ESCALATION_REQUIRED`, which is
    section 8's rule; (b) otherwise, if some usable offer produced a zero raw
    requirement, `NO_ORDER_NEEDED`; (c) otherwise, if every usable offer failed
    only the lead-time limit, `ESCALATION_REQUIRED`; (d) otherwise
    `NO_FEASIBLE_SUPPLIER`. Placing (b) above (c) keeps a SKU that provably
    needs nothing from raising an escalation.
16. **The 15-minute freshness bound of section 4.2 is applied to supplier
    order snapshots too**, since section 4.5 states the same bound for them.

### Outstanding orders

17. **An open supplier order whose supplier SKU has no configured mapping
    blocks every store SKU mapped to that supplier**, and is journalled as an
    `UNMAPPED_ORDER` run event. Section 5.4 says such an order "blocks the
    affected mapping" and "must not be silently omitted", but the application
    cannot tell which store SKU it affects. Blocking that supplier's SKUs is
    the reading that keeps the sentence meaningful and matches policy section
    14's refusal to assume a supplier has no open orders. An unmapped order
    that already carries a matching full receipt contributes nothing anywhere
    and does not block.
18. **Receipts are fetched once per supplier per run**, for every
    non-cancelled order in that supplier's snapshot, and then matched per SKU.
    This is one `get_receipts` call per supplier instead of one per SKU.

### Concurrency and recovery

19. **The process lock is an advisory `fcntl.flock` on `<database>.lock`.**
    Version 1 is explicitly single-worker; this is the smallest mechanism that
    also survives a process crash.
20. **Startup recovery only runs when the lock is free.** A second process
    must never declare a live worker's run interrupted.

### Local world and adapters

21. **Mock world file formats** (`inventory.json`, `sales.json`,
    `calendar.json`, `supplier_<ID>.json`, `raw_calls/<ID>.jsonl`) are an
    implementation choice. They are plain, hand-editable JSON so an operator
    can inspect and perturb external state directly.
22. **Snapshot ages are expressed as `as_of_offset_seconds` relative to the
    injected clock** (an explicit `as_of` is also accepted). This makes
    staleness scenarios reproducible without freezing the fixtures to one
    instant.
23. **Supplier behaviour queues** (`place_order_behaviors`,
    `lookup_behaviors`, `offer_failures`) let the mock world reproduce
    timeouts, lost responses, contradictory acceptances, rejections, and
    undecidable lookups. Each queue entry is consumed once, so a scenario
    replays deterministically. The `*` key applies to any supplier SKU or key.
24. **The mock supplier decrements its own availability on acceptance and
    derives the promised delivery date** as its local date plus the offer lead
    time. It owns that state, exactly as a real supplier would.
25. **`supplier-calls` reads the mock world's raw call log**, which exists only
    because these adapters are local doubles. It is documented as a mock-world
    inspection command; no production adapter is expected to provide one, and
    nothing in the application depends on it.
26. **`scheduler_poll_seconds`** (default 30) and **`--max-cycles`** are the
    two knobs added so the long-running scheduler can be demonstrated and
    tested without sleeping in real time. The specification fixes the daily
    schedule but not the polling cadence.

---

## 3. Test coverage against Section 16

| Required category | Tests |
|---|---|
| 1. Configuration, time-zone scheduling, catch-up, manual run, worker exclusion | `test_config.py`, `test_scheduling.py` |
| 2. 28-day normalization and smoothing, zeros, non-`NORMAL` multipliers, aggregate ceiling, Decimal | `test_forecast.py` |
| 3. External inventory changes; the app never mutates the ledger | `test_inventory_ledger.py` |
| 4. Outstanding quantity across every lifecycle and inconsistency | `test_outstanding.py`, `test_end_to_end.py` |
| 5. Coverage horizon, target, pack rounding, exposure | `test_planning.py` |
| 6. Selection in every branch, including ties | `test_selection.py`, `test_ordering.py` |
| 7. Normal accepted ordering, exact arguments, one raw call | `test_ordering.py` |
| 8. Price, spend, lead-time, and hard-maximum escalation with zero raw calls | `test_ordering.py` |
| 9. Rejection, offer failure, unavailable SKU, malformed response, no feasible supplier | `test_ordering.py` |
| 10. Missing/stale inventory, incomplete sales, missing calendar, malformed orders, mismatched receipts | `test_data_errors.py` |
| 11. Timeout and crash after dispatch, with no blind retry or fallback | `test_unknown_outcomes.py` |
| 12. Reconciliation to found, final-not-found, and still-unknown | `test_unknown_outcomes.py` |
| 13. Idempotency across restart and completed daily runs | `test_scheduling.py` |
| 14. An end-to-end world with several SKUs and coexisting outcomes | `test_end_to_end.py` |

Every test that could result in a purchase asserts the application decision,
the raw supplier call count, the exact raw call arguments, the authoritative
supplier world state, the relevant Inventory Ledger world state, and the
durable application journal.

Forecast expectations are stated independently — by closed form
(`10 * (7/10)**27 = 7**27 / 10**26`), by written-out two-step arithmetic, or by
a hand-computed constant — rather than by recomputing them through the
production helper.
