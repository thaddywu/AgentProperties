# SafeMA v2 mechanism validation

The 24 App 2 tests establish that policy denial occurs before the consequential
supplier effect and that authorization uses independently resolved state.

For every denied call the suite asserts:

```text
decision = DENY
raw place_order calls = 0
new supplier orders = 0
audit raw_invoked = 0
```

For the allowed complete Base App workflow it asserts:

```text
decision = ALLOW
raw place_order calls = 1
new supplier orders = 1
audit raw_invoked = 1
```

Coverage includes receiver identity, supplier-SKU and destination operands,
numeric types, offer price/pack/availability, owner limits, missing or changed
trusted configuration, snapshot completeness, units, cross-supplier
outstanding quantity, receipt consistency, and all relevant order lifecycle
states.

Run from the repository root:

```bash
PYTHONPATH=safema-v2:apps/multi-supplier-replenishment/v1/base-app/src:apps/multi-supplier-replenishment/v1/base-app:apps/multi-supplier-replenishment/v1/safema-v2 \
  python -m pytest -q apps/multi-supplier-replenishment/v1/safema-v2/tests
```
