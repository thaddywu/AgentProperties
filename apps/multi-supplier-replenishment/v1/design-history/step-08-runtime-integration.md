# Step 8 — SafeMA Runtime Integration

Progress after implementation: `[■■■■■■■■□□] 8/10`

The reusable runtime is `../../../../safema-v2/`. The App 2 integration is
`../safema-v2/replenishment_safema/`. The frozen Base App was not modified.

SafeMA v2 adds four generic mechanisms to the v1 core:

1. deployment-registered receiver-instance bindings;
2. live trusted-state resolver declarations and implementations;
3. actual call values in Effect attributes; and
4. strict exact numeric policy operators: `add`, `mul`, `mod`, `gt`, `gte`,
   `lt`, and `lte`.

For each intercepted call, the runtime binds positional arguments to the
Python signature, normalizes the Effect, invokes the App 2 trusted resolver,
evaluates YAML, records the decision, and invokes the original method only
after `ALLOW`.

The App 2 resolver reads the owner config and mock authoritative service world
directly rather than using Base App calculations. It pins the owner config
digest, strictly validates units/completeness/freshness, reads both supplier
order snapshots, fetches all relevant receipts including cancelled orders,
and derives outstanding quantity.

A pre-call denial is translated into:

```text
OrderRejected(code="SAFEMA_POLICY_DENIED", ...)
```

This preserves the frozen Base App supplier protocol and accurately indicates
that no order was created. The SafeMA audit separately records `DENY` and
`raw_invoked=0`.

The runnable integration entry point is `../safema-v2/runner.py`.
