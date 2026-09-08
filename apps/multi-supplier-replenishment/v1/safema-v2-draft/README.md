# App 2 purchase-ceiling model — meeting draft

Status: superseded design preview preserved for history. The implemented and
validated integration now lives in the sibling `safema-v2/` directory. This
draft remains intentionally non-executable.

This draft contains only the requested rule:

```text
on_hand(store_sku)
+ outstanding(store_sku)
+ proposed_quantity(store_sku)
<= hard_max(store_sku)
```

It is intentionally not a claim that the complete natural-language policy has
been encoded.

## Files

- `models/api-effects-purchase-v1.yaml` maps the delivered Base App's actual
  `LocalSupplierService.place_order(...)` arguments into a normalized
  `PURCHASE` effect.
- `policies/inventory-exposure-ceiling-v1.yaml` resolves the actual supplier
  SKU and destination against trusted metadata and applies the ceiling.

## Normalized effect

The actual method is called positionally, but SafeMA binds it to the Python
signature before normalization:

```text
PURCHASE(
  resource = actual supplier_sku,
  context = actual destination_id,
  attributes = {
    supplier_id: registered target binding,
    proposed_quantity: actual quantity,
    expected_unit_price: actual expected_unit_price,
    idempotency_key: actual idempotency_key,
    currency: USD
  }
)
```

Supplier identity comes from a deployment-registered binding for the
intercepted receiver instance, not from the mutable `receiver.supplier_id`
attribute or a Base App-supplied free-form argument.

## Trusted metadata contract

Before evaluation, a trusted resolver must obtain and validate fresh state
independently of the Base App and expose:

- a `replenishment_destination_authority` Context whose identity is the
  permitted destination and whose `store_id` is owner-controlled;
- a `supplier_sku_mapping` Resource whose identity is the supplier SKU and
  whose attributes contain the authoritative `supplier_id` and `store_sku`;
- an `inventory_exposure` Resource whose identity is the store SKU and whose
  attributes contain `store_id`, `active`, `base_unit`, `on_hand`,
  `outstanding`, and `hard_max`.

`on_hand` comes from the Inventory Ledger. `outstanding` must be independently
derived from fresh complete order snapshots from both suppliers plus Inventory
Ledger receipts. `hard_max` and the mapping come from owner-controlled
configuration. Missing, stale, incomplete, malformed, or contradictory state
must prevent creation of the trusted record and therefore fail closed.

## Minimal generic runtime extension required

The current SafeMA v1 language permits only literal Effect attributes and the
policy operators `eq`, `subset`, `exists`, `all`, and `any`. This draft needs:

1. actual call selectors and trusted target-binding selectors in Effect
   attributes;
2. deployment-registered receiver-instance binding;
3. strict numeric `add`, `gt`, and `lte` operators; and
4. fail-closed numeric type handling, with no string concatenation or implicit
   floating-point conversion.

Decimal and integer values should remain exact. These are candidate generic
SafeMA v2 features; no runtime implementation is included in this meeting
draft.
