# Trust boundary

Trusted for authorization:

- SafeMA v2 runtime, models, resolver code, and audit sidecar;
- deployment registration of concrete supplier receiver instances;
- owner configuration read and digest-pinned independently;
- Inventory Ledger records and receipts after strict validation; and
- complete current supplier order and offer state after strict validation.

Untrusted for authorization:

- Base App planner, config objects, journal, logs, and cached calculations;
- Base App-provided on-hand, outstanding, store-SKU, or hard-max claims;
- idempotency-key text as a source of SKU identity; and
- unregistered or mismatched supplier objects.

Actual supplier SKU, quantity, price, destination, and idempotency key are
Effect operands. They describe what the raw call would do; policy evaluates
them but does not treat them as authority.

The local prototype assumes the deployment controls model/config/world files
and that there is no hostile in-process memory attacker. Production isolation
is outside the case-study guarantee.
