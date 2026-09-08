# Step 5 — Base App Inspection and Conformance Audit

Progress after inspection: `[■■■■■□□□□□] 5/10`

Inspection date: 2026-09-03

The Base App was inspected as delivered in `../base-app/`. The inspection did
not patch or otherwise adapt the Base App for SafeMA. The frozen specification
and policy hashes still match `FROZEN-ARTIFACTS.md`:

- `app-spec-v1.md`:
  `8d4c4b3cc3d57d8d457a76f7057d5e9a8996401587e99550b3bde728d3634a98`
- `policy-v1.md`:
  `6381653ecf275dfd5f537ce6fd71644deb782e185daead265ab989c2e0ba3966`

## Overall result

The implementation is complete, runnable, deterministic, local/offline, and
substantially conforms to the frozen application specification. Its normal
forecasting, planning, supplier ranking, durable-attempt, unknown-outcome,
scheduling, and reporting paths are implemented rather than stubbed.

The audit also found three clear fail-open discrepancies and one receipt
identity observability gap at the mock service boundary. These are recorded
below rather than repaired. They are useful, application-grounded failure
cases for later baseline/treatment evaluation, but they remain Base App
defects relative to the frozen specification and policy.

No SafeMA code, terminology, network dependency, LLM dependency, or hidden
enforcement integration is present in the Base App.

## Actual structure

The package is `src/replenishment` and is divided into conventional modules:

- `interfaces.py` and `domain.py`: external protocols and typed domain values;
- `adapters/`: local deterministic clock, inventory, sales, calendar, and two
  supplier implementations;
- `engine.py`: run orchestration and per-SKU workflow;
- `forecast.py`, `planning.py`, `selection.py`, and `outstanding.py`: the
  deterministic business calculations;
- `execution.py` and `reconciliation.py`: effect submission and unknown-outcome
  recovery;
- `journal.py`, `storage.py`, and `locking.py`: SQLite state, transactions, and
  the single-worker lock;
- `scheduler.py`, `reporting.py`, and `cli.py`: operator entry points; and
- `tests/` plus `fixtures/`: deterministic local world and test suite.

The only external-state mutation exposed by an application interface is the
supplier `place_order` operation. SQLite writes are internal operational state,
and the local supplier adapter mutates its mock supplier world to emulate that
external effect. Inventory, sales, calendar, supplier snapshots, and
idempotency lookup are read operations.

## External boundaries and authoritative reads

The protocols in `interfaces.py` match the frozen boundaries:

| Boundary | Actual operation | Role in the run |
|---|---|---|
| Clock | `now()` | Fixed run instant, timestamps, and local business date |
| Inventory Ledger | `get_snapshot(store_id, skus)` | Atomic on-hand, active, unit, and SKU state |
| Inventory Ledger | `get_receipts(store_id, supplier_id, order_ids)` | Posted receipts used to remove orders from outstanding quantity |
| POS Sales History | `get_daily_sales(store_id, sku, start_date, end_date)` | Exact 28-day history |
| Calendar | `get_days(store_id, start_date, end_date)` | Historical normalization and future multipliers |
| Supplier A/B | `get_offer(supplier_sku, destination_id)` | Current offer for candidate construction |
| Supplier A/B | `get_order_snapshot(destination_id)` | Authoritative order lifecycle state |
| Supplier A/B | `lookup_by_idempotency_key(destination_id, key)` | Unknown-attempt reconciliation |
| Supplier A/B | `place_order(...)` | The sole consequential external mutation |

The engine reads the Inventory Ledger snapshot once before per-SKU planning.
It then reads both suppliers' complete order snapshots and receipt state before
sales, calendar, and offer evaluation. Outstanding quantity is derived from
authoritative supplier orders and Inventory Ledger receipts, including orders
not created by this app when their supplier-SKU mapping is unambiguous.

## Exact consequential effect boundary

There are two supplier instances, but one shared effect shape:

```text
SupplierService.place_order(
    supplier_sku: str,
    quantity: int,
    expected_unit_price: Decimal,
    destination_id: str,
    idempotency_key: str,
) -> PlaceOrderResult
```

The concrete calls are positional. Supplier identity is not an argument; it is
the identity of the selected adapter object in
`services.suppliers[selected.supplier_id]`. The call path is:

```text
ReplenishmentEngine._execute
  -> Journal.commit_attempt                 # durable DISPATCHING record
  -> execution.place_purchase_order
  -> selected SupplierService.place_order   # consequential boundary
  -> LocalSupplierService.place_order       # local raw mock effect
```

The interface declaration is `interfaces.py:75`; the actual outbound call is
`execution.py:107`; the local raw implementation is
`adapters/supplier.py:331`. The attempt is committed in `journal.py:355` before
the outbound call. The idempotency key is:

```text
replenishment/<run_id>/<store_sku>/<supplier_id>
```

SafeMA may therefore need to mediate both supplier objects' `place_order`
methods, normalize the adapter identity into supplier identity, and evaluate
the five actual call operands. No other Base App external mutation boundary
was found.

## Identity, lifecycle, and algorithms

- Store SKUs are case-sensitive opaque strings owned by the Inventory Ledger
  and matched to owner configuration. Supplier SKUs are related through the
  configured per-supplier mapping; reverse mappings must be unambiguous.
- Supplier order states are `ACCEPTED`, `SHIPPED`, `DELIVERED`, and
  `CANCELLED`. Attempts separately use `DISPATCHING`, `ACCEPTED`, `REJECTED`,
  and `OUTCOME_UNKNOWN`.
- `ACCEPTED`, `SHIPPED`, and unreceipted `DELIVERED` orders contribute their
  full quantity. Valid full receipts remove that quantity. `CANCELLED` orders
  contribute zero. Unknown attempts block only their SKU and are reconciled
  before planning.
- Forecasting implements the exact 28-day calendar-normalized Decimal
  exponential smoothing procedure. It sums unrounded future daily forecasts
  before applying one ceiling.
- Planning uses `coverage_days = lead_time + 1 + safety_days`, subtracts
  `on_hand + outstanding`, and rounds a positive requirement to one supplier
  pack.
- Selection first filters executable candidates. If any candidate avoids
  projected stockout, it ranks by total cost, lead time, unit price, and
  supplier ID. If all candidates remain at risk, lead time becomes the first
  ranking key. It does not split an order or fall back after rejection.
- Inventory-snapshot failure is fatal for the run. Per-SKU malformed data,
  unusable offers, owner-limit escalation, definitive rejection, and unknown
  effects are represented as distinct outcomes. Dispatch uncertainty is not
  treated as rejection.

## Test and runnable-demo evidence

`python -m pytest -q` passes. Collection reports 224 tests, covering
configuration, data errors, forecasting, planning, outstanding quantities,
selection, ordering, unknown outcomes, scheduling, and end-to-end behavior.

An isolated copy of the supplied fixtures also completed through the real CLI
and produced `RUN-000001` with the expected mix of accepted, skipped,
escalated, rejected, and unknown outcomes. The run required no network access.

The four discrepancy probes below were executed only in temporary directories;
they did not alter the delivered Base App or its fixtures.

## Recorded discrepancies

### D1 — A receipt for a cancelled order is invisible to orchestration

Severity: high conformance and authorization impact.

The specification says that a receipt for a `CANCELLED` order is inconsistent
and must block the SKU (`app-spec-v1.md`, Section 5.4). The policy likewise
requires inconsistent receipts to block ordering (`policy-v1.md`, Sections 5
and 6).

In `engine.py:296-304`, receipt IDs are requested only for orders whose status
is not `CANCELLED`. Consequently the later outstanding calculation cannot see
a receipt attached to a cancelled order, even though its lower-level function
can reject such an input.

Reproduction result:

```text
world: CANCELLED order + matching posted receipt
expected: DATA_ERROR, zero place_order calls
observed: ORDER_ACCEPTED, one place_order call
```

### D2 — A missing supplier snapshot completeness flag becomes `True`

Severity: high fail-open completeness impact.

The frozen contract requires every `OrderSnapshot` to contain a completeness
flag and forbids ordering from incomplete or malformed state. In
`adapters/supplier.py:225`, the local adapter evaluates:

```text
document.get("snapshot_complete", True)
```

Absence is therefore silently converted into an affirmative completeness
claim instead of an unusable snapshot.

Reproduction result:

```text
world: SUPPLIER_A snapshot with snapshot_complete omitted
expected: affected SKU blocked, zero place_order calls
observed: ORDER_ACCEPTED, one place_order call
```

### D3 — A missing authoritative inventory base unit becomes `EACH`

Severity: high unit/quantity authorization impact.

The Inventory Ledger owns `base_unit`; each record must contain it, and missing
authoritative data must not be guessed. In `adapters/inventory.py:72`, the local
adapter evaluates:

```text
raw.get("base_unit", BASE_UNIT)
```

An absent unit is thus accepted as `EACH`, allowing quantity calculations and
submission without authoritative unit evidence.

Reproduction result:

```text
world: active SKU record with base_unit omitted
expected: DATA_ERROR, zero place_order calls
observed: ORDER_ACCEPTED, one place_order call
```

### D4 — Receipt identity disagreement can be filtered before validation

Severity: medium boundary-observability gap; its practical interpretation
depends on whether supplier order IDs are globally unique or supplier-scoped.

The policy requires receipt and order identities to agree and says conflicting
state is not permission to continue. In `adapters/inventory.py:114-115`, a
receipt whose supplier ID differs from the requested supplier is discarded
before the reconciliation code can validate it. If the ledger contains a
receipt referring to a requested order ID but carrying the wrong supplier ID,
the Base App cannot distinguish that contradiction from absence.

Reproduction result under the frozen document's identity-agreement reading:

```text
world: open SUPPLIER_A order + receipt with the same order ID but SUPPLIER_B
expected: DATA_ERROR for identity disagreement
observed: NO_ORDER_NEEDED; the A order remained outstanding and no error was reported
```

This probe did not cause an excess order because the unseen receipt left more
outstanding inventory in the calculation. It is still a reporting and
state-integrity discrepancy. Step 6 should define the trusted receipt lookup
and identity model explicitly instead of relying on silent filtering.

## Additional audit notes

- The decision journal is rich for executable candidates and effects, but some
  early-exit/no-requirement records summarize excluded suppliers rather than
  preserving every offer and supplier-specific planning value named in
  specification Section 5.6. This is a low-severity accountability gap, not an
  observed authorization bypass.
- Offer identity is normalized by the adapter from the request context when a
  local raw offer omits `supplier_sku` or `destination_id`. The typed `Offer`
  returned to the application always contains both. Step 6 must decide whether
  that adapter context is trusted, rather than assuming the raw payload echoed
  those fields.
- An unrelated untracked root file, `agent-spec-recletter.py`, appeared outside
  the App 2 directory. Its origin was not established, it is not imported by
  this Base App, and it was not modified or removed during this inspection.

## Step 6 handoff facts

The architecture step should begin from the actual effect boundary above, not
from a hypothetical `place_order(sku, quantity)` API. In particular it must
account for:

1. supplier identity residing in the receiver/adapter instance;
2. store-SKU identity requiring trusted reverse resolution of supplier plus
   supplier SKU;
3. destination, quantity, and expected price being direct call operands;
4. `on_hand`, unit, active status, receipts, order lifecycle, completeness, and
   owner limits requiring independently trusted resolution;
5. outstanding quantity requiring cross-supplier aggregation and receipt/order
   reconciliation; and
6. fail-closed handling for missing, stale, malformed, or contradictory
   trusted state.

This completes Step 5 only. No SafeMA architecture or executable model has
been designed here.
