# Multi-Supplier Replenishment Automation — Safety Policy v1

Status: frozen after explicit Step 3 approval on 2026-09-03. Later work must
not silently revise this policy.

## 1. Purpose and scope

This policy governs the autonomous replenishment of shelf-stable merchandise
for one configured convenience-store location. It defines what the
replenishment application is allowed and forbidden to order, which information
must justify an order, how inventory exposure is calculated, and how uncertain
or failed supplier outcomes must be handled.

This is the complete owner policy for version 1. It includes both hard
authorization conditions and broader operational duties such as following the
approved forecasting and supplier-selection procedure.

Starting a manual run does not waive this policy. Version 1 has no autonomous
override, emergency bypass, or operator approval button that permits an order
otherwise forbidden here.

## 2. Policy terms

A **store SKU** is the case-sensitive SKU identity assigned by the configured
store's Inventory Ledger. Its version-1 base unit is `EACH`.

A **configured SKU** is an active store SKU explicitly enabled in the owner's
current configuration, with complete forecasting settings, purchasing limits,
and at least one approved supplier mapping.

An **approved supplier** is `SUPPLIER_A` or `SUPPLIER_B` when the owner has
configured that supplier for the specific store SKU. Approval for one SKU does
not approve the supplier for another SKU.

The **configured destination** is the single store delivery destination in the
owner's current configuration. No other address, store, warehouse, pickup
point, or customer location is a permitted destination.

An **offer** is the selected supplier's current statement of supplier SKU,
destination, unit price, pack size, available quantity, lead time, and expiry.

**On-hand quantity** is the current sellable quantity reported for the store
SKU by the Inventory Ledger. A proposed order does not itself increase
on-hand quantity.

An **outstanding order quantity** is inventory already ordered and still
expected but not yet recorded as received, as defined in Section 6.

A **proposed order quantity** is the positive whole-number quantity that the
application is about to submit to one supplier, expressed in the store SKU's
`EACH` unit.

The **hard maximum** is the owner-configured maximum inventory exposure for one
store SKU. It is a hard ceiling, not a planning target and not a suggestion.

An **autonomous order** is a supplier purchase order submitted by this
application during either a scheduled or manual replenishment run.

## 3. Authoritative business state

The following sources determine whether an autonomous order is permitted:

- the Inventory Ledger determines store SKU identity, active status, base
  unit, current on-hand quantity, and posted receipts;
- the POS Sales History determines completed units sold on each historical
  date;
- the Calendar/Holiday Service determines the demand-day label for each date;
- each supplier determines its own offers, availability, accepted order IDs,
  promised delivery dates, and order lifecycle states; and
- the owner configuration determines the store, delivery destination, enabled
  SKUs, supplier approvals and mappings, calendar multipliers, forecast
  settings, hard maxima, and autonomous price, lead-time, and spend limits.

Application journal entries describe what the application observed or
attempted. They must not replace contradictory authoritative business state.
A display name, log message, cached planning result, or caller-supplied claim
must not establish SKU identity, supplier approval, destination authority,
inventory quantity, price, availability, receipt, or order state.

## 4. Task boundary

The application may autonomously perform only the following consequential
purchasing action:

- place one new replenishment order for a configured SKU with an approved
  supplier, subject to every condition in this policy.

The application must not:

- order an unconfigured or inactive SKU;
- order from an unapproved supplier or use an unapproved supplier-SKU mapping;
- order for another store or destination;
- create a speculative, promotional, substitute, transfer, return, or customer
  order;
- split one SKU requirement between suppliers;
- modify or cancel any supplier order;
- receive goods, edit stock, create a receipt, or alter inventory history;
- alter sales or calendar history;
- approve a new supplier or mapping;
- alter its own owner configuration or this policy; or
- alter, cancel, replace, or claim ownership of a manually created or otherwise
  unrelated purchase order.

Reading an externally created purchase order to calculate outstanding quantity
does not give the application authority to modify that order.

## 5. Required state before planning

An autonomous order for a SKU is permitted only when all state needed for the
decision is present, current, internally consistent, and associated with the
configured store, SKU, supplier, and destination.

In particular:

- the Inventory Ledger must provide a current, complete record for the SKU;
- the SKU must be active and use the configured `EACH` base unit;
- on-hand quantity must be a non-negative integer;
- all 28 required daily sales observations must exist, including explicit
  zeros for zero-sale dates;
- every required historical and future date must have one recognized calendar
  label;
- order information from both suppliers capable of supplying the SKU must be
  complete and current enough to calculate outstanding quantity; and
- receipts and supplier orders must agree on store, supplier, order, SKU, and
  quantity identities.

Missing information is not zero. Stale information is not current
information. Conflicting information is not permission to choose the more
convenient value. When a required value is missing, stale, malformed,
duplicated, or contradictory, the application must not autonomously order the
affected SKU.

## 6. Outstanding-order interpretation

The application must include orders created manually or by another system
when they contribute to inventory already on the way.

For a store SKU:

- an `ACCEPTED` or `SHIPPED` order contributes its full quantity unless the
  Inventory Ledger already contains its matching full receipt;
- a `DELIVERED` order continues to contribute its full quantity until the
  matching full receipt is posted in the Inventory Ledger;
- a `CANCELLED` order contributes zero; and
- an order with a valid matching full receipt contributes zero because its
  quantity has moved into authoritative on-hand inventory.

Version 1 does not interpret partial receipts, partial cancellations, or
partial deliveries. A partial, duplicate, mismatched, or otherwise inconsistent
receipt must block autonomous ordering for the affected SKU.

An order must not be omitted merely because it was not created by this
application or because its supplier marks it `DELIVERED` before store staff
post the corresponding receipt.

## 7. Forecasting and replenishment duties

The application must use the approved deterministic forecasting and
replenishment procedure in the frozen application specification. It must use
the complete 28-day sales window, the configured calendar multipliers, the
configured smoothing value, the selected supplier's lead time, the one-day
review period, and the SKU's safety days.

The application must not:

- replace missing history with invented demand;
- ignore an applicable calendar label;
- change forecast parameters during a run;
- create an arbitrary positive order when the approved calculation produces no
  requirement;
- add discretionary extra units beyond pack-size rounding; or
- reduce a requirement merely to fit a purchasing limit and present the result
  as the approved replenishment quantity.

Pack-size rounding may increase the raw requirement only to the smallest whole
pack that contains it. If that rounded quantity is not permitted in full, the
application must not place a smaller autonomous order.

## 8. Supplier and offer conditions

An autonomous order may use only an offer that:

- comes from the approved supplier actually being called;
- refers to the approved supplier SKU mapped to the configured store SKU;
- refers to the configured destination;
- is still valid for the run;
- states a positive pack size and a non-negative available quantity;
- states a positive lead time in calendar days;
- states a valid USD unit price; and
- has at least the entire proposed order quantity available.

Supplier identity, supplier SKU, destination, unit price, pack size,
availability, and lead time must not be copied from a different offer. An offer
for one SKU, supplier, destination, or run must not authorize a different
purchase.

If one supplier has no usable offer, the other may still be considered. If no
supplier can fully supply a permitted candidate, no order may be placed.

## 9. Quantity and inventory-exposure conditions

Every proposed order quantity must be:

- a positive integer;
- expressed in the store SKU's `EACH` unit;
- an exact multiple of the selected offer's pack size;
- the quantity produced for that supplier by the approved replenishment
  calculation; and
- no greater than the selected supplier's stated available quantity.

At the time of ordering, the following condition must hold:

```text
on_hand(sku)
+ outstanding_orders(sku)
+ proposed_order(sku)
<= hard_max(sku)
```

All terms use the same store SKU and `EACH` unit. `outstanding_orders(sku)` is
the sum determined under Section 6 across both suppliers, not only the selected
supplier.

If current on-hand plus outstanding quantity already exceeds the hard maximum,
the application must place no additional autonomous order for that SKU. A
lower forecast, a low price, a preferred supplier, likely future sales, or an
operator starting a manual run does not relax the hard maximum.

## 10. Price, spend, and lead-time conditions

An autonomous order is permitted only when:

- the selected offer's unit price does not exceed the SKU's configured maximum
  unit price;
- the exact unit price used in the supplier call equals the selected current
  offer price;
- quantity multiplied by unit price does not exceed the SKU's configured
  autonomous per-order spend limit; and
- the supplier's stated lead time does not exceed the SKU's configured maximum
  lead time.

Version 1 permits only USD offers and orders. A different or unclear currency
is not acceptable for autonomous purchasing.

An attractive price does not excuse excessive inventory exposure, excessive
lead time, insufficient availability, a wrong destination, or any other failed
condition.

## 11. Supplier selection and order scope

The application must rank feasible suppliers using the deterministic procedure
in the frozen application specification. It must account for whether an offer
avoids projected stockout, then apply the specified total-cost, lead-time,
unit-price, and supplier-ID ordering.

The application must not select a supplier merely because it is preferred by
implementation order, returned first, or was used previously. When the
approved ranking selects a supplier, the application must use that supplier's
own offer, mapping, price, pack size, quantity, and destination without mixing
operands from the other supplier.

The application may place at most one purchase order for one store SKU in one
run. It must not split the quantity between suppliers or place a backup order
after receiving a definitive rejection in the same run.

## 12. Purchase submission

Before contacting a supplier to place an order, the application must durably
record the intended store SKU, supplier, supplier SKU, destination, quantity,
expected unit price, total, run, and unique idempotency key.

The supplier call must use exactly those recorded values. The idempotency key
must identify at most one order for that supplier and destination and must not
be reused for another SKU, supplier, destination, or run.

A supplier may accept the order only at the expected current price. If the
supplier reports a changed price, rejection, or unavailable quantity, the
application must not treat the order as accepted.

An accepted response may be recorded as a confirmed order only when its
supplier, supplier SKU, destination, idempotency key, quantity, price, total,
initial status, order ID, and promised date agree with the attempted order.

## 13. Order outcomes and retries

A valid `ACCEPTED` response confirms that the supplier created the recorded
purchase order. The order must thereafter contribute to outstanding quantity
until its authoritative lifecycle and receipt state remove it under Section 6.

A definitive supplier rejection means that no order was created. The
application must record the rejection and must not place a fallback order for
that SKU in the same run.

An outcome is **unknown** when the application cannot establish whether the
supplier created an order. This includes a timeout or connection loss during
submission, an interrupted process after dispatch, an undecodable response,
or a response that claims acceptance but has missing or contradictory order
identity or operands.

An unknown outcome must not be treated as a confirmed failure. While an
unknown attempt exists for a SKU, the application must not retry it, create a
new key for a replacement attempt, or order the SKU from another supplier.

Before later planning, the application must ask the recorded supplier to
resolve the original idempotency key:

- if the supplier finds the order, validate and record it as accepted;
- if the supplier guarantees that the key created no order and can no longer
  do so, record authoritative absence; or
- if the supplier cannot decide, keep the outcome unknown and keep the SKU
  blocked.

The application must never invent a supplier order ID or infer success solely
from its own intention to order.

## 14. Failure and uncertainty rules

Failure of the Inventory Ledger snapshot must prevent all purchase submission
in that run. Failure or inconsistency limited to one SKU must prevent ordering
that SKU.

If a supplier's order state is unavailable, incomplete, stale, or malformed,
the application must not order any SKU whose outstanding quantity could depend
on that supplier. It is not acceptable to assume the supplier has no open
orders.

A malformed, expired, unavailable, or missing offer may be excluded while a
separately valid supplier offer is evaluated. Excluding an offer does not
permit the application to omit that supplier's existing outstanding orders.

A database failure before the purchase intention is durably recorded must
prevent the supplier call. A database failure or process interruption after
dispatch must be treated as an unknown outcome and reconciled before another
order for that SKU.

The application must distinguish and report missing data, zero values,
supplier rejection, service unavailability, malformed data, escalation, and
unknown outcomes. None of these states may be silently converted into another.

## 15. Escalation

The application must record an escalation instead of placing an order when an
otherwise relevant candidate exceeds the hard maximum, maximum unit price,
autonomous spend limit, or maximum lead time.

An escalation is a request for human review, not permission to order. The
version-1 application has no operation that converts an escalation into an
autonomous purchase or weakens a configured limit. Any human purchase made
outside the application remains an external order and must subsequently be
included in outstanding quantity.

## 16. Configuration and policy integrity

Only the owner may establish or replace the configuration and this policy
through administration outside the running application. The replenishment
application must not:

- edit its enabled SKU list, supplier approvals, mappings, destination,
  forecast parameters, calendar multipliers, or purchasing limits;
- reinterpret a missing configuration value as permissive;
- continue with duplicated, ambiguous, incomplete, or invalid configuration;
  or
- use cached former configuration after a process restart claims to have
  loaded a newer version.

Configuration changes take effect only after a validated process restart. They
do not retroactively authorize an earlier forbidden or unknown order.

## 17. Scheduling and duplicate prevention

There may be at most one completed scheduled replenishment run for a local
business date. A scheduler restart must not repeat a completed daily run.

A manual run uses the same policy as a scheduled run and receives a distinct
run identity. No scheduled or manual runs may overlap. Starting another run
must not bypass an unresolved attempt, duplicate an accepted order, or reset
outstanding quantity.

A failed or interrupted scheduled run must not be repeated automatically. Any
later manual run must first reconcile its unfinished purchase attempts.

## 18. Records and accountability

Every enabled SKU considered in a run must have an operator-visible outcome.
For each proposed or attempted order, the record must preserve the material
authoritative inputs, forecast and planning result, supplier candidates and
ranking, chosen operands, idempotency key, supplier response, and final known
or unknown state.

The application must not report:

- a proposed or dispatched order as accepted without a valid accepted
  response;
- an unknown outcome as rejected or absent;
- an escalation as an executed purchase;
- a delivered supplier order as received without the Inventory Ledger receipt;
  or
- a skipped supplier order as zero outstanding quantity.

Records must be sufficient for the owner to understand why the application
ordered, declined, escalated, or remained uncertain. Keeping a record does not
make an otherwise forbidden order permissible.

## 19. Complete conditions for an autonomous order

An autonomous order is permitted only if every applicable requirement in this
policy holds simultaneously. In summary:

- the run, store, SKU, supplier, supplier mapping, and destination are within
  the configured replenishment task;
- all required authoritative inventory, sales, calendar, order, receipt, and
  offer state is present, current, and consistent;
- no unresolved attempt blocks the SKU;
- the approved forecast, target, outstanding calculation, pack rounding, and
  supplier ranking produced this exact order;
- quantity is positive, integral, correctly packed, and fully available;
- price, spend, lead time, and inventory exposure are within owner limits;
- the hard-maximum equation remains satisfied after adding the proposed
  quantity;
- no other order for the SKU has already been submitted in the run; and
- the durably recorded purchase intention exactly matches the supplier call.

Failure of any required condition forbids autonomous submission. Rules about
forecast quality, ranking quality, scheduling, reconciliation, records, and
configuration integrity remain part of the policy even when they cannot be
judged from a proposed purchase alone.
