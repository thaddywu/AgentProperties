# Step 2 — Specification Notes

Progress after drafting: `[■■□□□□□□□□] 2/10`

## Important decisions

1. Inventory and supplier quantities share the Inventory Ledger's integer
   `EACH` unit. Pack sizes affect rounding but do not introduce another unit.
2. Forecasting uses 28 complete daily observations, calendar-normalized
   exponential smoothing with `alpha = 0.30`, and future calendar multipliers.
3. Planning is a daily periodic-review, supplier-specific order-up-to model.
   Supplier lead time changes the coverage horizon and therefore the candidate
   quantity.
4. An order remains outstanding after supplier `DELIVERED` until the Inventory
   Ledger contains its matching full receipt. This avoids a gap between
   delivery status and authoritative on-hand posting.
5. Supplier selection first handles projected stockout risk, then total cost,
   lead time, unit price, and supplier ID with explicit deterministic ordering.
6. Placement uncertainty is durable state. The app reconciles by idempotency
   key and does not blindly retry or switch suppliers.

## Intentionally unspecified implementation choices

- Python package/module/class names and the exact SQLite table layout.
- Exact CLI command names, provided the required scheduler, manual-run, and
  inspection capabilities exist in both JSON and readable forms.
- Concrete mock fixture values beyond the fixed algorithms and constraints.
- Production authentication, networking, and vendor adapter details, because
  the reference Base App is fully local/offline.
- Report styling and scheduler polling interval.

These choices do not alter observable application behavior defined by
`../app-spec-v1.md`.
