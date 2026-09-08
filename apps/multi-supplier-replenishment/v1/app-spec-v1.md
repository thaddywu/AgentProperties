# Multi-Supplier Replenishment Automation — Application Specification v1

Status: frozen after explicit Step 2 approval on 2026-09-03. Later work must
not silently revise this specification.

## 1. Purpose

The Multi-Supplier Replenishment Automation is a continuously running local
application for one independently operated urban convenience store. Once per
local business day, it reads authoritative inventory, sales, calendar, and
supplier state; forecasts near-term demand for configured shelf-stable SKUs;
decides whether and how much to replenish; selects one of two approved
suppliers; and places purchase orders that fall within the owner's configured
autonomous purchasing limits.

The application is deterministic. Given the same configuration, run time, and
external-service responses, it must produce the same forecasts, decisions,
supplier ranking, and effect calls.

The application does not require or use an LLM. It must remain useful and
runnable without any external enforcement system.

## 2. Users and operating model

The primary user is the store owner or inventory manager. The user:

- configures the store, delivery destination, enabled SKUs, approved supplier
  mappings, forecasting parameters, and purchasing limits;
- leaves the application running so that it performs the daily workflow;
- may request the same workflow manually;
- reviews run, per-SKU decision, purchase-attempt, and exception records; and
- resolves supplier outcomes that remain unknown.

A receiving clerk uses the external Inventory Ledger, not this application, to
record delivery receipts against supplier order IDs. Sales staff use the POS
system. Neither role needs access to the replenishment application.

Version 1 is a local Python command-line application with a long-running
scheduler command and explicit run/report commands. It persists only its own
operational state in SQLite. Exactly one worker may execute a replenishment run
at a time. Concurrent workers and distributed reservations are out of scope.

## 3. Time, units, currency, and arithmetic

- The configured store time zone is an IANA time-zone name. Business dates and
  the daily schedule use this zone. Persisted timestamps use RFC 3339 UTC.
- A `business_date` is the local calendar date containing the run; version 1
  schedules every calendar date, including weekends and holidays.
- A run captures one immutable `run_started_at` from the injected clock. All
  expiry and freshness decisions in that run use this value.
- Every configured SKU uses the Inventory Ledger's base unit `EACH`. All
  inventory, sales, offer availability, receipt, and order quantities are
  non-negative integers in that unit.
- Version 1 supports USD only. Monetary values use decimal arithmetic and have
  exactly two fractional digits. Binary floating-point arithmetic is forbidden
  for prices, costs, forecasts, or multipliers.
- Forecast calculations use decimal precision of at least 28 significant
  digits. Intermediate values are not rounded. A required inventory quantity
  is rounded once with mathematical ceiling as specified below.
- SKU and supplier identifiers are case-sensitive opaque strings after config
  validation. Application code must not infer identity from display names.

## 4. External service boundaries

All external interfaces are synchronous. Production adapters may contact real
systems, but the version-1 implementation and tests must provide complete
local deterministic implementations and require no cloud or vendor account.

### 4.1 Clock

`Clock.now()` returns one timezone-aware instant. Tests must be able to inject a
fixed clock.

### 4.2 Inventory Ledger

The Inventory Ledger is authoritative for store SKU identity, base unit,
active status, current sellable `on_hand`, and receipts. It exposes:

```text
get_snapshot(store_id, skus) -> InventorySnapshot
get_receipts(store_id, supplier_id, order_ids) -> list[Receipt]
```

`InventorySnapshot` contains one revision ID, one `as_of` timestamp, and zero
or one `InventoryRecord` for every requested SKU. One call represents an atomic
ledger snapshot. Each record contains `store_id`, `sku`, `base_unit`, `active`,
and integer `on_hand`.

A `Receipt` contains a stable receipt ID, store ID, supplier ID, supplier order
ID, store SKU, integer received quantity, and posting timestamp. Version 1
allows at most one receipt per supplier order and does not support partial
receipt. The receipt quantity must equal the order quantity.

The application never calls an inventory mutation operation. Placing a
purchase order does not change `on_hand`. POS sales, receiving, and authorized
manual stock adjustments change inventory outside this application.

An inventory snapshot is usable only when its store ID and requested SKU
records match the request, its revision and timestamp are present, it is not
from the future relative to `run_started_at`, and it is no more than 15 minutes
old. Missing, duplicate, negative, inactive, wrong-unit, or malformed records
are unusable for the affected SKU. Failure to obtain any snapshot is fatal to
the run and no purchase calls may be made.

### 4.3 POS Sales History

The sales service is authoritative for completed POS sales. It exposes:

```text
get_daily_sales(store_id, sku, start_date, end_date) -> list[DailySales]
```

Each record contains store ID, SKU, one local business date, and non-negative
integer `units_sold`. The inclusive requested range is the 28 business dates
immediately before the run's local business date. The response must contain
exactly one record for each date. A zero is observed zero demand; a missing date
is unknown and must not be replaced with zero. Returns, waste, shrinkage, and
manual corrections are not sales and do not alter this history.

Missing, duplicate, negative, wrong-store, wrong-SKU, out-of-range, or
malformed sales data makes that SKU ineligible for autonomous ordering in the
run. Another SKU may still be processed.

### 4.4 Calendar/Holiday Service

The calendar service is authoritative only for assigning one demand-day label
to each local date. It exposes:

```text
get_days(store_id, start_date, end_date) -> list[CalendarDay]
```

The fixed labels are:

- `NORMAL`
- `WEEKEND`
- `PRE_HOLIDAY`
- `HOLIDAY`

The owner configuration maps every label to a positive decimal demand
multiplier. The external service does not choose the multiplier. A date has
exactly one label; the calendar adapter resolves any real-world overlap before
returning it.

For each SKU, the app requires calendar records for the 28 historical sales
dates and every future date that could appear in a candidate supplier's
coverage horizon. Missing, duplicate, unknown-label, wrong-store, or malformed
calendar data blocks autonomous ordering for that SKU.

### 4.5 Supplier services

There are exactly two configured supplier IDs in version 1: `SUPPLIER_A` and
`SUPPLIER_B`. Each adapter exposes:

```text
get_offer(supplier_sku, destination_id) -> Offer | NotOffered
get_order_snapshot(destination_id) -> OrderSnapshot
lookup_by_idempotency_key(destination_id, key) -> LookupResult
place_order(
    supplier_sku,
    quantity,
    expected_unit_price,
    destination_id,
    idempotency_key,
) -> PlaceOrderResult
```

An `Offer` contains supplier ID, supplier SKU, destination ID, USD unit price,
positive integer pack size, non-negative available quantity, positive integer
lead time in calendar days, and `valid_until`. Available quantity and any
order quantity are expressed in the store SKU's `EACH` unit and must be pack
multiples. `NotOffered` is a valid response and means the supplier cannot be a
candidate for that SKU in this run.

The supplier must interpret `expected_unit_price` as a compare-and-place
condition: it may accept the order only at that exact price; otherwise it must
return a definitive rejection. An idempotency key identifies at most one order
for that supplier and destination.

`OrderSnapshot` contains the supplier ID, destination ID, an `as_of` timestamp,
a completeness flag, and purchase orders. It must be a complete view of every
`ACCEPTED`, `SHIPPED`, `DELIVERED`, or `CANCELLED` order that can affect the
destination's current inventory exposure, including orders created outside
this application. Version 1 imposes no history-retention cutoff on an
unreceipted `DELIVERED` order. An incomplete snapshot is unusable. Its `as_of`
must not be in the future relative to `run_started_at` or more than 15 minutes
old.

`lookup_by_idempotency_key` returns exactly one of:

- `FOUND` with the authoritative purchase order;
- `NOT_FOUND_FINAL`, meaning the supplier guarantees that the key created no
  order and can no longer do so; or
- `UNKNOWN`, meaning absence cannot be established.

## 5. Data ownership and application data model

### 5.1 Ownership summary

| Data | Authoritative owner |
|---|---|
| SKU identity, base unit, active status, `on_hand` | Inventory Ledger |
| Historical units sold | POS Sales History |
| Date labels | Calendar/Holiday Service |
| Label multipliers and purchasing limits | Owner configuration |
| Offer, price, availability, lead time | Corresponding supplier |
| Supplier order ID and lifecycle status | Corresponding supplier |
| Physical receipt | Inventory Ledger |
| Run, decision, and attempt journal | Replenishment application |

Application journal data records what the app observed and attempted. It never
overrides contradictory authoritative external state.

### 5.2 SKU configuration

Each enabled SKU configuration contains:

- `sku` and display name;
- `hard_max`, a non-negative integer inventory-exposure ceiling;
- `safety_days`, an integer from 0 through 14;
- `max_lead_time_days`, an integer from 1 through 14;
- `max_unit_price_usd`, a positive two-decimal amount;
- `autonomous_order_limit_usd`, a positive two-decimal amount; and
- one supplier-SKU mapping for each supplier that is approved to supply it.

At least one of the two suppliers must be mapped. A missing mapping means that
supplier is not approved for the SKU. `hard_max` applies to total exposure in
store units, regardless of pack size or supplier.

### 5.3 Purchase order

An authoritative supplier `PurchaseOrder` contains:

- supplier ID and supplier order ID;
- idempotency key;
- destination ID;
- supplier SKU and mapped store SKU;
- positive integer quantity;
- USD unit price and total cost;
- `ACCEPTED`, `SHIPPED`, `DELIVERED`, or `CANCELLED` status;
- creation time; and
- promised delivery date for non-cancelled orders.

`REJECTED` is a placement outcome, not a purchase-order state, because no order
exists. Order modification, partial cancellation, partial shipment, and
partial delivery are unsupported.

### 5.4 Outstanding quantity

For one SKU, authoritative outstanding quantity is computed from supplier
orders and Inventory Ledger receipts:

- `ACCEPTED` or `SHIPPED`: full order quantity unless a matching full receipt
  already exists;
- `DELIVERED`: full order quantity until a matching full receipt exists;
- `CANCELLED`: zero; and
- any order with a valid matching full receipt: zero.

A receipt matches only when store ID, supplier ID, supplier order ID, store SKU,
and quantity all match. Duplicate receipts, partial receipts, a receipt for a
cancelled order, or identity/quantity disagreement is a data inconsistency and
blocks that SKU rather than being guessed.

Outstanding quantity includes orders created manually or by another system if
the supplier returns them and they map unambiguously to a configured store SKU.
An open order with an unknown supplier-SKU mapping blocks the affected mapping;
the application must not silently omit it.

### 5.5 Run record

A `Run` contains a monotonic ID such as `RUN-000001`, trigger kind
`SCHEDULED` or `MANUAL`, local business date, start/end timestamps, source
snapshot identifiers, and one status:

- `RUNNING`
- `COMPLETED`
- `COMPLETED_WITH_EXCEPTIONS`
- `FAILED`

One scheduled run record may exist per local business date. Manual runs have
distinct IDs. A completed scheduled run is not repeated.

### 5.6 SKU decision record

Every enabled SKU receives one durable record containing all material inputs
and derived values: history window, smoothed base demand, future multipliers,
on-hand quantity, contributing outstanding orders, each supplier offer,
candidate target and rounded quantity, ranking, chosen supplier, final outcome,
and reason.

Outcomes include at least:

- `NO_ORDER_NEEDED`
- `ORDER_ACCEPTED`
- `SUPPLIER_REJECTED`
- `BLOCKED_UNKNOWN_ATTEMPT`
- `DATA_ERROR`
- `NO_FEASIBLE_SUPPLIER`
- `ESCALATION_REQUIRED`

### 5.7 Purchase attempt

Before calling `place_order`, the app commits a `PurchaseAttempt` containing
run ID, SKU, supplier, destination, quantity, expected price, total cost, and a
stable idempotency key. Its state is one of:

- `DISPATCHING`
- `ACCEPTED`
- `REJECTED`
- `OUTCOME_UNKNOWN`

An attempt begins as `DISPATCHING`. A valid accepted response stores the
supplier order ID and becomes `ACCEPTED`. A definitive rejection becomes
`REJECTED`. Any loss of response, timeout, process recovery from
`DISPATCHING`, malformed accepted response, or inability to prove the outcome
becomes `OUTCOME_UNKNOWN`.

## 6. Deterministic forecasting model

### 6.1 Inputs

For SKU `k`, let the 28 dates immediately preceding the run date be ordered
oldest to newest as `d1 ... d28`.

- `sales(k, dt)` is the authoritative integer units sold on date `dt`.
- `label(dt)` is the calendar label for that date.
- `multiplier(label(dt))` is its configured positive decimal multiplier.
- `alpha` is one global configured decimal satisfying `0 < alpha <= 1`. The
  version-1 default is exactly `0.30`.

### 6.2 Normalize historical demand

Calendar effects are removed from each historical observation:

```text
normalized(k, dt) = sales(k, dt) / multiplier(label(dt))
```

### 6.3 Exponential smoothing

Initialize from the oldest normalized observation:

```text
smooth(k, d1) = normalized(k, d1)
```

For `t = 2 ... 28`:

```text
smooth(k, dt) = alpha * normalized(k, dt)
              + (1 - alpha) * smooth(k, d(t-1))
```

The final base daily forecast is `base(k) = smooth(k, d28)`. No special
startup estimate, missing-value imputation, trend term, or seasonal term is
used. Twenty-eight complete days are mandatory, including explicit zero-sale
days.

### 6.4 Future daily forecast

For a future local date `f`, including the run date:

```text
forecast(k, f) = base(k) * multiplier(label(f))
```

Forecast demand over an inclusive sequence of future dates is the exact sum of
their unrounded daily forecasts. Integer demand for planning is the
mathematical ceiling of that aggregate. The app must not independently round
each day.

This model intentionally has no learned parameters, stochastic sampling,
promotion inference, censored-demand correction, or manual forecast override.

## 7. Replenishment planning

### 7.1 Daily review period

The review period is exactly one calendar day because the application runs
daily. For a usable supplier offer with lead time `L` and SKU safety setting
`S`, its coverage horizon is:

```text
coverage_days = L + 1 + S
```

The first covered date is the run's local business date. The last is
`coverage_days - 1` dates later.

### 7.2 Supplier-specific order-up-to target

For each offer independently:

```text
target_inventory = ceil(sum of forecast over coverage_days)
inventory_position = on_hand + outstanding_quantity
raw_requirement = max(0, target_inventory - inventory_position)
```

If `raw_requirement` is positive, round it up to the supplier's pack size:

```text
order_quantity = ceil(raw_requirement / pack_size) * pack_size
```

If `raw_requirement` is zero, that supplier produces no purchase candidate.
Outstanding quantity is counted once and is never added separately per
supplier.

### 7.3 Inventory exposure

For a proposed candidate:

```text
exposure_after_order = on_hand
                     + outstanding_quantity
                     + order_quantity
```

The candidate is not autonomously executable when this value exceeds the
SKU's configured `hard_max`. Version 1 does not reduce the quantity to squeeze
under a limit because that would knowingly create an order that fails to reach
the computed target. It records `ESCALATION_REQUIRED` when the otherwise usable
candidate fails an owner purchasing limit.

If `on_hand + outstanding_quantity` already exceeds `hard_max`, the app records
`ESCALATION_REQUIRED` before fetching offers and places no order for the SKU.

### 7.4 Projected stock before arrival

For ranking, the candidate arrival date is the run date plus `L` calendar days.
Expected supply before arrival is `on_hand` plus outstanding orders whose
promised delivery date is on or before that arrival date. Expected demand
before arrival is the ceiling of the aggregate forecast from the run date
through the day before arrival. A candidate `avoids_stockout` when expected
supply before arrival is at least expected demand before arrival.

This projection ranks candidates; it does not alter authoritative `on_hand` or
outstanding quantity.

## 8. Candidate feasibility and supplier selection

An offer produces an executable candidate only when all of the following hold:

- the supplier is one of the two configured suppliers and is mapped for the
  SKU;
- the offer identities match the requested supplier SKU and destination;
- the offer is unexpired at `run_started_at`;
- price, pack size, availability, and lead time have valid types and units;
- lead time does not exceed the SKU's `max_lead_time_days`;
- the rounded positive quantity is no more than available quantity;
- unit price is no more than `max_unit_price_usd`;
- quantity times unit price is no more than
  `autonomous_order_limit_usd`; and
- exposure after the order is no more than `hard_max`.

If an otherwise valid candidate exceeds an owner price, spend, lead-time, or
exposure limit, the app records it as requiring escalation. It does not place
the order. Insufficient supplier availability is simply infeasible. Version 1
does not split, cap, or combine quantities.

Supplier selection is deterministic:

1. If no executable candidate exists, place no order. Use
   `ESCALATION_REQUIRED` if at least one candidate failed only an owner limit;
   otherwise use `NO_FEASIBLE_SUPPLIER`.
2. If one or more candidates avoid projected stockout, discard candidates that
   do not.
3. If no candidate avoids projected stockout, retain all candidates and rank
   shortest lead time first to minimize the projected shortage interval.
4. In the stockout-avoiding set, rank lowest total order cost first, then
   shortest lead time, then lowest unit price, then supplier ID.
5. In the all-at-risk set, rank shortest lead time first, then lowest total
   order cost, then lowest unit price, then supplier ID.
6. The first candidate is selected. Supplier IDs compare as uppercase ASCII,
   so `SUPPLIER_A` wins a final tie over `SUPPLIER_B`.

Thus price, availability, and lead time all affect the decision without a
non-reproducible score or optimizer.

## 9. Purchase execution

Before an effectful call, the application commits the complete purchase
attempt and idempotency key in SQLite. The key is:

```text
replenishment/<run_id>/<store_sku>/<supplier_id>
```

It then calls the selected supplier's `place_order` exactly once with the
candidate's actual supplier SKU, rounded quantity, expected unit price, the
single configured destination, and that key.

For an accepted result, the app validates the returned supplier, supplier SKU,
destination, idempotency key, quantity, unit price, total, status, order ID, and
promised date against the attempted values. A valid result must start in
`ACCEPTED`; it is stored and reported as `ORDER_ACCEPTED`.

A structured rejection definitively creates no order. The attempt becomes
`REJECTED`, the SKU outcome is `SUPPLIER_REJECTED`, and the app does not fall
back to the other supplier in the same run.

A timeout, connection loss during placement, undecodable response, missing or
contradictory accepted-result field, or process interruption after the
`DISPATCHING` commit has an unknown external outcome. The attempt becomes or is
recovered as `OUTCOME_UNKNOWN`. The app must not call another supplier or retry
that SKU until reconciliation establishes the outcome.

The Base App must call no supplier mutation other than this specified
`place_order` operation.

## 10. Unknown-outcome reconciliation

At the start of every run, before reading planning inputs or placing any order,
the app processes all `DISPATCHING` and `OUTCOME_UNKNOWN` attempts in stable
attempt-ID order.

It calls the recorded supplier's `lookup_by_idempotency_key`:

- `FOUND`: validate the order exactly as an accepted placement response, store
  its order ID, and resolve the attempt to `ACCEPTED`;
- `NOT_FOUND_FINAL`: resolve the attempt to `REJECTED`, with a reason indicating
  authoritative absence; or
- `UNKNOWN`, service failure, or malformed response: retain
  `OUTCOME_UNKNOWN`.

Any unresolved attempt blocks autonomous ordering only for the same store SKU,
not every SKU. A found order participates in outstanding quantity during the
same run. Reconciliation never generates a replacement order itself.

## 11. Scheduling and run orchestration

The default schedule is 05:00 in the configured store time zone. The scheduler
must:

- run once when that local time is reached;
- on startup after 05:00, run once if no scheduled run exists for that local
  date; and
- do nothing if that date's scheduled run is already completed or completed
  with exceptions.

A failed or interrupted scheduled run is not retried automatically. The
operator may inspect it and start a manual run; unknown attempts are reconciled
before that manual run can plan new orders.

The operator may invoke a manual run, which uses identical logic and creates a
new run ID. A process-level exclusive lock and a database check reject a manual
or scheduled start while another run is `RUNNING`. No two runs overlap.

After reconciliation, a run obtains the inventory snapshot before any purchase
call. It then processes configured SKUs in ascending SKU order. An error for
one SKU is journaled and processing continues unless the inventory snapshot is
wholly unavailable or malformed, the database cannot commit, or an invariant
needed by all SKUs fails. A run with at least one per-SKU exception ends as
`COMPLETED_WITH_EXCEPTIONS`; a fatal run-level error ends as `FAILED`.

## 12. Failure handling

The application must never invent a missing value or silently claim an
external outcome.

- **Inventory service unavailable:** fail the run before purchase execution.
- **Missing or bad inventory record:** record `DATA_ERROR` for that SKU and do
  not order it.
- **Missing/malformed sales or calendar data:** record `DATA_ERROR` for that
  SKU and do not order it.
- **Supplier order snapshot unavailable, incomplete, stale, or malformed:** do
  not plan any SKU
  whose outstanding quantity may depend on that supplier. Other provably
  unaffected SKUs may continue.
- **One offer API unavailable, malformed, expired, or `NotOffered`:** exclude
  that supplier and evaluate the other. Journal the exclusion.
- **Both offers unusable or no candidate fully available:** record
  `NO_FEASIBLE_SUPPLIER`; make no purchase call.
- **Owner limit exceeded:** record `ESCALATION_REQUIRED`; make no purchase
  call.
- **Structured placement rejection:** record `SUPPLIER_REJECTED`; do not try
  another supplier during that run.
- **Placement timeout or uncertain/malformed outcome:** record
  `OUTCOME_UNKNOWN`; do not retry or use another supplier until reconciled.
- **Malformed authoritative order or receipt:** record `DATA_ERROR` and block
  that SKU.
- **Journal commit failure before placement:** do not call the supplier.
- **Journal commit failure after a placement call:** recovery treats the
  durable `DISPATCHING` attempt as unknown and reconciles by idempotency key.

Every skip, exclusion, error, reconciliation result, and external call outcome
must be visible in the durable journal and operator report.

## 13. Configuration

Configuration is an owner-managed JSON or TOML file loaded at startup. It
contains:

- store ID, destination ID, IANA time zone, and daily run time;
- SQLite database path;
- external adapter factory declarations and local options;
- exactly two supplier declarations with IDs `SUPPLIER_A` and `SUPPLIER_B`;
- forecast `alpha`, default `0.30`;
- one positive multiplier for every fixed calendar label; and
- the enabled SKU records defined in Section 5.2.

The implementation must reject the entire configuration before starting the
scheduler if required fields are missing, unknown fields are present, IDs are
duplicated, numeric ranges are invalid, money has more than two decimals,
calendar labels are incomplete, a supplier mapping is ambiguous, or an adapter
cannot be constructed.

Configuration is reloaded only on process restart. The running application
does not edit its own configuration or approve suppliers dynamically.

## 14. Inspection interface

The CLI must provide machine-readable JSON and readable text forms for:

- current scheduler status and last completed run;
- list and detail views of runs;
- per-SKU decisions and the inputs used;
- purchase attempts, including unknown outcomes and reconciliation history;
- recorded supplier order IDs and statuses; and
- a manual-run command.

Reports must distinguish zero, missing, rejected, unavailable, malformed, and
unknown values. They must not display a proposed order as accepted.

## 15. Persistence and restart behavior

SQLite is the authoritative store only for application-owned records. Schema
creation and migrations occur explicitly at startup. Each run, decision, and
attempt has stable primary keys and timestamps.

The attempt must be committed before `place_order`. Accepted/rejected state
updates and decision records must be transactional where they concern the same
response. On restart, any durable `RUNNING` run is marked failed-interrupted,
and every `DISPATCHING` attempt is treated as `OUTCOME_UNKNOWN` for subsequent
reconciliation.

The application may cache external responses only inside one run. A later run
must read authoritative services again. Deleting or recreating the app database
does not modify inventory, supplier orders, sales, or calendar state.

## 16. Required testing

All tests must be deterministic, local, and offline. Test doubles must model
external state separately from the application database and expose their raw
call history.

At minimum, tests must cover:

1. configuration validation, time-zone scheduling, daily catch-up, manual run,
   and single-worker exclusion;
2. the exact 28-day normalization and exponential-smoothing formula, including
   zero sales, non-`NORMAL` multipliers, aggregate ceiling, and Decimal use;
3. inventory changes from external sales, receipt, and adjustment fixtures,
   while proving the app never mutates the ledger;
4. outstanding quantity for accepted, shipped, delivered-unreceived,
   delivered-received, cancelled, externally created, and inconsistent orders;
5. supplier-specific coverage horizon, order-up-to target, pack rounding, and
   exposure calculation;
6. selection when both suppliers are feasible, only one has availability, one
   avoids stockout, neither avoids stockout, costs tie, and final IDs tie-break;
7. normal accepted ordering with exact actual arguments and one raw call;
8. price, spend, lead-time, and hard-maximum escalation with zero raw calls;
9. supplier rejection, offer failure, unavailable SKU, malformed response, and
   no feasible supplier;
10. missing/stale inventory, incomplete sales, missing calendar dates,
    malformed orders, and mismatched receipts, without guessed values;
11. placement timeout and crash-after-dispatch, proving no blind retry or
    fallback occurs;
12. unknown reconciliation to found, final-not-found, and still-unknown;
13. idempotency across scheduler restart and completed daily runs; and
14. an end-to-end world with several SKUs in which normal orders, no-order
    decisions, escalation, one supplier failure, and an unknown outcome coexist.

Every effect-related test must assert the supplier raw-call count, exact call
arguments, authoritative supplier world state, application journal state, and
operator-visible outcome.

## 17. Application boundaries and non-goals

Version 1 does not include:

- multiple stores, warehouses, or stock transfers;
- fresh goods, recipes, unit conversion, lots, serial numbers, expiry, or
  recalls;
- promotions beyond the supplied calendar labels;
- demand censoring or lost-sales estimation;
- partial receipt, partial shipment, backorder, order editing, or cancellation;
- split orders, substitutions, cross-SKU optimization, or budget allocation;
- invoices, payment, tax, accounting, returns, or contract negotiation;
- supplier discovery or dynamic supplier approval;
- automatic inventory corrections or receiving;
- real cloud/vendor dependencies in the reference implementation;
- concurrent workers, distributed locks, or reservation protocols; and
- probabilistic, machine-learned, or LLM-driven decisions.

These exclusions are part of the version-1 contract, not unspecified features
that an implementer should add.
