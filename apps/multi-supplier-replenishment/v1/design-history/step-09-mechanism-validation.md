# Step 9 — Mechanism Validation

Progress after mechanism validation: `[■■■■■■■■■□] 9/10`

The executable validation suite is
`../safema-v2/tests/test_runtime.py`. It contains 24 tests, all passing.
The shared v2 numeric core has another four passing tests.

Validation covers:

- legal Base App workflow reaches the raw supplier method after `ALLOW`;
- hard-max violation is denied before the raw method;
- unregistered supplier receiver;
- wrong destination;
- missing base unit or on-hand value;
- missing supplier snapshot completeness evidence;
- accepted, shipped, delivered, cancelled, and received lifecycle behavior;
- cancelled order with a receipt;
- malformed quantity and price operands;
- wrong supplier-SKU operand, price, pack multiple, or availability;
- forged/corrupted Base App in-memory hard maximum;
- owner config mutation after SafeMA startup; and
- invalid policy YAML operator.

Every denied-call helper verifies all four mechanism facts:

1. policy result is `DENY`;
2. raw `place_order` call count is zero;
3. no new supplier order appears in world state; and
4. the SafeMA audit has `raw_invoked=0`.

The legal workflow verifies `ALLOW`, one raw call, one created order, and
`raw_invoked=1`. A full supplied-fixture run also completed through the SafeMA
runner with four authorized purchases and four raw invocations.

The independent frozen Base App suite remains green with 224 collected tests.
The completed Recommendation Submission Base App currently contains unrelated
pre-existing invalid `safema.install(..yaml)` lines and therefore was not used
as a regression gate for this App 2 change.
