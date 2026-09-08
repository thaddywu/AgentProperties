# Step 7 — Executable Models

Progress after model definition: `[■■■■■■■□□□] 7/10`

The formal SafeMA v2 artifacts are isolated in `../safema-v2/`:

- API Effect Model: `models/api-effects-v2.yaml`;
- trusted metadata origins: `models/trusted-origins-v2.yaml`;
- live trusted-state declarations: `models/trusted-state-resolvers-v2.yaml`;
- executable policy: `policies/replenishment-purchase-v2.yaml`; and
- complete owner-policy mapping: `POLICY-MAPPING.md`.

The actual supplier method becomes one `PURCHASE` Effect. Supplier identity is
obtained from a deployment-registered receiver binding; supplier SKU,
destination, quantity, expected price, and idempotency key come from the actual
call.

The policy independently enforces identity alignment, active `EACH` inventory,
positive pack-aligned quantity, availability, price/currency, price/spend/lead
limits, complete authoritative state, and:

```text
on_hand + outstanding + proposed_quantity <= hard_max
```

Forecast correctness, target calculation, global supplier ranking,
scheduling, and Base App report completeness remain explicitly outside the
executable subset. The model does not pretend those whole-application duties
can be proven from one purchase call.

The earlier `safema-v2-draft/` meeting preview is preserved as design history
but is superseded by these validated formal artifacts.
