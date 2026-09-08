# Step 1 — Application Shape

Started at: `[□□□□□□□□□□] 0/10`

Completed proposal: `[■□□□□□□□□□] 1/10`

## 1. Concise application description

Version 1 is a continuously running, deterministic replenishment application
for one independently operated urban convenience store. Each morning before
opening, it reads authoritative stock and sales data, forecasts demand for the
store's configured shelf-stable SKUs, accounts for inventory already on the
way, compares current offers from two approved suppliers, and places at most
one purchase order per SKU when replenishment is needed.

The store owner or inventory manager configures the SKUs and operating limits
and reviews run results and exceptions. Store staff continue to sell and
receive goods through the store's existing systems; the automation never
edits the stock ledger itself.

## 2. Architecture diagram

```text
                         owner / inventory manager
                         | configure + review exceptions
                         v
+-------------+     +-------------------------------------+     +-------------+
| POS sales   |---->| Multi-Supplier Replenishment App    |<--->| Supplier A  |
| history     |     |                                     |     | offers/POs  |
+-------------+     | - demand forecast                   |     +-------------+
                    | - replenishment plan                |
+-------------+     | - deterministic supplier selection |     +-------------+
| Calendar /  |---->| - purchase execution + run journal |<--->| Supplier B  |
| holidays    |     +-------------------------------------+     | offers/POs  |
+-------------+                       ^                         +-------------+
                                      |
                              read stock + receipts
                                      |
                              +------------------+
 store sales and receiving -->| Inventory Ledger|
 staff                         | authoritative    |
                              +------------------+
```

The POS system feeds sales to the Inventory Ledger as part of the store's
normal operation. The application reads both services but does not own or
repair that external synchronization.

## 3. Actors and services

### Human actors

- **Store owner / inventory manager:** chooses enabled SKUs, approved
  suppliers, the delivery location, operating thresholds, and autonomous
  purchasing limits; reviews orders, blocked decisions, and unknown outcomes.
- **Receiving clerk:** receives a physical delivery and posts the receipt,
  linked to its supplier order ID, in the Inventory Ledger.
- **Sales staff / customers:** cause sales through the POS system. They do not
  interact with the replenishment application directly.

### Authoritative external services

- **Inventory Ledger:** authoritative for the store SKU catalog, SKU base unit,
  current `on_hand`, sale/consumption postings, manual adjustments, and receipt
  postings. Only sales, receiving, and authorized store adjustments change
  `on_hand`.
- **POS Sales History:** authoritative for time-stamped units sold per SKU and
  is the demand-history input. It does not authorize an inventory quantity.
- **Supplier A and Supplier B services:** each is authoritative for its own SKU
  offers, current unit price, availability, promised lead time, accepted order
  IDs, and subsequent order status.
- **Calendar/Holiday service:** authoritative for the store's local business
  dates and configured holiday/event labels used as forecast signals.

All of these boundaries will be implemented locally with deterministic mocks
in the Base App case study; they still model systems outside the application.

## 4. Core state

### Externally owned state read by the application

- Store SKU identity, base unit, and active/inactive status.
- Current `on_hand` quantity for each store SKU.
- Historical daily units sold per SKU.
- Inventory receipt records linked to supplier order IDs.
- Supplier-specific SKU identity mapping and current offer data.
- Supplier purchase orders and their lifecycle states.
- Local calendar dates and holiday/event classifications.

### Application-owned state

- Owner-maintained configuration: enabled SKUs, the single delivery location,
  approved suppliers, forecasting parameters, replenishment targets and hard
  inventory maxima, maximum acceptable prices, and autonomous spend limits.
- A durable journal of scheduled runs, per-SKU decisions, external request
  correlation IDs, returned supplier order IDs, failures, and unresolved
  unknown outcomes.
- The last successfully completed run time. Forecast values and offers are
  reproducible run outputs, not competing sources of inventory truth.

## 5. Lifecycle summary

### Inventory lifecycle

`inventory` means sellable physical units at this one store, expressed in the
Inventory Ledger's base unit for each SKU.

1. A completed POS sale posts consumption and decreases ledger `on_hand`.
2. A receiving clerk confirms a delivery against a supplier order ID; the
   receipt posting increases ledger `on_hand`.
3. Authorized manual adjustments can correct damage, shrinkage, or count
   differences and may increase or decrease `on_hand`.
4. The replenishment application only reads these records. Placing an order
   does not itself increase `on_hand`.

### Purchase-order lifecycle

- A successful supplier call returns an authoritative order ID in `ACCEPTED`.
- The supplier may move it to `SHIPPED`, then `DELIVERED`, or to `CANCELLED`.
- A supplier may return `REJECTED` without creating an active order.
- A timeout or lost response is recorded locally as `OUTCOME_UNKNOWN`; the app
  must reconcile it instead of assuming either success or failure.

For planning, `outstanding_orders(sku)` is the quantity still expected but not
yet posted as received: accepted or shipped quantity, plus delivered quantity
until a matching Inventory Ledger receipt exists. Cancelled, rejected, and
fully received orders contribute zero. Version 1 has no partial deliveries;
therefore an order is either wholly unreceived or wholly received. An
unresolved unknown attempt is not guessed into a numeric quantity; it blocks
another autonomous order for that SKU until reconciliation prevents a blind
duplicate.

## 6. Recurring workflow

The application runs in one worker once each local business day before the
store opens. The operator may also request the identical workflow manually;
there is no separate stock-update event pipeline in version 1.

For each run, the worker:

1. reconciles prior unknown attempts and refreshes supplier order states;
2. obtains calendar signals and a consistent set of inventory and sales reads;
3. processes enabled SKUs in stable SKU order;
4. derives a deterministic demand forecast and target stock;
5. subtracts `on_hand` and outstanding quantity to obtain any net requirement;
6. fetches offers from the two approved suppliers;
7. deterministically selects one feasible supplier and order quantity;
8. places the order with a unique correlation ID only when all normal business
   conditions permit autonomous execution; and
9. records every decision, skip, failure, and returned order ID in the run
   journal for operator review.

The exact forecasting equation, calendar adjustment, target-stock formula,
rounding, supplier ranking, and failure behavior are deliberately reserved for
Step 2, where they will be specified reproducibly.

## 7. Base App boundary and explicit exclusions

The Base App owns scheduling, forecasting, planning, supplier selection,
purchase orchestration, durable run/attempt journaling, and operator-facing
reports. It does not own the authoritative services listed above.

Version 1 intentionally excludes:

- multiple stores, warehouse transfers, and shared inventory;
- fresh/perishable goods, lots, serial numbers, expiration dates, and recalls;
- recipes, ingredient conversions, substitutions, and cross-SKU optimization;
- partial deliveries, backorders, split sourcing, and order modification;
- receiving goods, correcting stock, cancelling supplier orders, invoices,
  payment, accounting, and returns;
- supplier onboarding, price negotiation, contracts, and unapproved vendors;
- real vendor/cloud integrations, concurrent workers, and distributed locks;
- machine-learned or LLM-based forecasting and autonomous configuration
  changes.

## 8. Unresolved questions

There are no blocking application-shape questions. Step 2 must make the
already bounded choices exact: time windows, forecast parameters, holiday
multipliers, target-stock formula, pack-size/rounding semantics, deterministic
supplier tie-breaking, snapshot freshness, idempotency, and each failure path.

## 9. Concrete-domain recommendation

Use the **single-location urban convenience store** for version 1.

- It maps customer sales directly to the same SKU units that are replenished,
  unlike a restaurant where recipes, waste, and ingredient-unit conversion can
  dominate the design.
- It avoids the lot, expiry, chain-of-custody, and patient-safety concerns that
  would make a clinic stockroom or laboratory either unrealistic when omitted
  or unnecessarily broad when included.
- Holiday-driven demand, two competing suppliers, frequent repeat ordering,
  and a hard stock-exposure ceiling remain natural and meaningful.

This domain is concrete enough to specify authoritative inventory behavior
without adding complexity solely for the case study.
