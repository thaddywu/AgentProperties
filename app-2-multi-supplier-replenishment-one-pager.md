# SafeMA: Runtime Enforcement for Autonomous Purchasing

## Overview and motivating scenario

A convenience-store replenishment application runs every day. It reads current
inventory, sales history, calendar signals, offers, supplier orders, and
receipts; forecasts demand; chooses between two suppliers; and places a
purchase order. The application is deterministic and contains no LLM, but a
bug or stale interpretation can still create a real financial and inventory
effect.

The owner sets one hard safety constraint for each store SKU:

```text
on_hand + outstanding_orders + proposed_order <= hard_max
```

The Base App implements this rule, but SafeMA does not trust the Base App's
calculation. It checks the actual supplier call against independently resolved
inventory, order, receipt, mapping, destination, and owner-limit state before
the raw supplier API is invoked.

## System model and guarantee

```text
Inventory Ledger -----+
Supplier A orders ----+--> trusted exposure resolver --+
Supplier B orders ----+                               |
Owner configuration --+                               v
                                                    policy
Base App place_order --> normalized PURCHASE --------+----> ALLOW --> supplier
                                                         |
                                                         +----> DENY (no order)
```

For a modeled and intercepted `place_order` call, SafeMA permits the raw
supplier API only when the actual order would keep trusted inventory exposure
at or below the owner's hard maximum. Missing, stale, incomplete, malformed,
or contradictory trusted state fails closed. Unmodeled or bypassed effect
channels remain outside this guarantee.

## The unchanged Base App

The Base App remains independently runnable and useful. Its normal flow is:

```text
daily trigger
  -> read inventory and existing supplier orders
  -> forecast 28-day calendar-adjusted demand
  -> calculate supplier-specific replenishment quantities
  -> rank feasible offers
  -> durably record a purchase attempt
  -> selected_supplier.place_order(...)
```

The Step 5 audit found that the implementation is substantial and its 224
tests pass. It also found realistic fail-open boundaries, including a cancelled
order receipt that orchestration does not fetch and missing unit/completeness
fields that local adapters default. SafeMA is therefore evaluated against
ordinary application faults rather than an artificial unsafe demo API.

## Actual effect boundary

The delivered Base App ultimately invokes:

```python
supplier.place_order(
    supplier_sku,
    quantity,
    expected_unit_price,
    destination_id,
    idempotency_key,
)
```

There are two supplier instances but one concrete Python method:

```text
replenishment.adapters.supplier.LocalSupplierService.place_order
```

Supplier identity is established by a deployment-registered binding for the
selected receiver object. The other five values are actual call operands, even
though the Base App passes them positionally.

## API Effect Model

The deployer models that method as a generic `PURCHASE` effect:

```yaml
target:
  callable: replenishment.adapters.supplier.LocalSupplierService.place_order
  receiver_binding: registered_instance
effect:
  kind: PURCHASE
  resources:
    from: {select: $call.args.supplier_sku}
    cardinality: one
    class: supplier_sku
  contexts:
    from: {select: $call.args.destination_id}
    cardinality: one
    class: delivery_destination
  attributes:
    supplier_id: {select: $target.binding.supplier_id}
    proposed_quantity: {select: $call.args.quantity}
    expected_unit_price: {select: $call.args.expected_unit_price}
    idempotency_key: {select: $call.args.idempotency_key}
    currency: {literal: USD}
```

Thus the authorization decision is based on what the supplier is actually
asked to do, not on a planner's earlier claim.

## Trusted state

SafeMA must independently bind the actual effect to three pieces of trusted
metadata:

| Trusted object | Identity | Required state |
|---|---|---|
| Destination authority | actual destination | owner-controlled `store_id` |
| Supplier-SKU mapping | actual supplier SKU | supplier ID and store SKU |
| Inventory exposure | resolved store SKU | store, active state, unit, on-hand, outstanding, hard maximum |

The Inventory Ledger owns on-hand, active state, base unit, and receipts. Both
supplier systems own their order lifecycle state. Owner-controlled
configuration owns the destination, mapping, and hard maximum. Base App
journal entries and planner intermediates are not authorization facts.

## Minimal declarative ceiling policy

After matching destination and supplier-SKU identities, the core YAML
predicate is:

```yaml
lte:
  - add:
      - {select: $trusted_inventory.attributes.on_hand}
      - {select: $trusted_inventory.attributes.outstanding}
      - {select: $effect.attributes.proposed_quantity}
  - {select: $trusted_inventory.attributes.hard_max}
```

The complete executable policy also requires a positive proposed quantity, an
active SKU, the `EACH` unit, the correct store and supplier mapping, exact pack
rounding, sufficient availability, the current USD price, and owner price,
spend, and lead-time limits.

## Example decision

Suppose the Base App attempts to order 40 units:

```text
trusted on_hand       = 55
trusted outstanding  = 20
actual proposed      = 40
owner hard_max       = 100
```

SafeMA evaluates `55 + 20 + 40 = 115`, so the policy returns `DENY` and the
raw supplier method is not called. If the proposed quantity were 20, exposure
would be 95 and this particular rule would allow it.

## Baseline / treatment result

Seven paired cases used fresh identical worlds. Five injected faults were
grounded in the delivered Base App: omitted Supplier A outstanding state,
`SHIPPED` misread as `CANCELLED`, missing inventory unit, an inconsistent
cancelled-order receipt, and a corrupted in-memory hard maximum.

| Metric | Baseline | SafeMA |
|---|---:|---:|
| Policy-violating effects reaching raw supplier API | 5 | 0 |
| Legitimate workflows completed | 2/2 | 2/2 |
| False denials | 0 | 0 |
| Raw purchase calls | 6 | 1 |

Every treatment denial occurred before the raw method and created no supplier
order. The normal accepted-order and normal no-order workflows were preserved.

## Status and scope

The case study is complete. The shared reusable implementation is
`safema-v2/`; App 2's executable models, trusted resolver, tests, audit, and
evaluation are in `apps/multi-supplier-replenishment/v1/safema-v2/`.

The natural-language policy remains broader than the executable subset.
Forecast quality, globally correct supplier ranking, scheduler behavior, and
Base App report completeness remain application obligations. SafeMA guarantees
only modeled, successfully intercepted effect channels; it is a
provenance-aware effect reference monitor, not a whole-program taint tracker.
