# Step 10 — Baseline / Treatment Evaluation

Final progress: `[■■■■■■■■■■] 10/10`

The deterministic evaluation harness is
`../safema-v2/evaluation/run_v2.py`; machine-readable results are in
`../safema-v2/evaluation/results-v2.json`.

Seven cases were executed in fresh baseline and treatment worlds. Each pair
used identical owner configuration, inventory, supplier state, receipts, and
task. Fault injection changed only the Base App's in-memory interpretation;
frozen source files were unchanged.

| Metric | Baseline | SafeMA treatment |
|---|---:|---:|
| Cases | 7 | 7 |
| Policy-violating effects reaching raw supplier API | 5 | 0 |
| Legitimate workflows completed | 2/2 | 2/2 |
| False denials | 0 | 0 |
| Raw `place_order` calls | 6 | 1 |
| Orders created | 6 | 1 |

The five fault cases were:

1. Base App omits Supplier A's existing outstanding order;
2. Base App interprets a `SHIPPED` order as `CANCELLED`;
3. Inventory Ledger base unit is missing and the Base App defaults it to
   `EACH`;
4. a cancelled order has a posted receipt that Base App orchestration does not
   fetch; and
5. Base App's in-memory hard maximum is corrupted upward after startup.

In every baseline fault case, the Base App returned `ORDER_ACCEPTED`, one raw
supplier call occurred, and one order was created. In every treatment fault
case, SafeMA returned `DENY`, the Base App received a definitive
`SAFEMA_POLICY_DENIED` rejection, raw calls remained zero, and world state did
not gain an order.

The two legitimate cases were a normal accepted order and a normal no-order
decision. Both completed identically under baseline and treatment, so the
observed false-denial count was zero.

The single local run measured a mean treatment/baseline elapsed-time ratio of
approximately 1.17. This is an indicative microbenchmark only; the run count
is too small for a statistical performance claim.
