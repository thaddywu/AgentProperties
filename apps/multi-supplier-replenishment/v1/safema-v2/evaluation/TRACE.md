# Baseline / Treatment Trace

| Case | Expected | Baseline raw/order | Treatment decision | Treatment raw/order |
|---|---|---:|---|---:|
| Normal order | ALLOW | 1 / 1 | ALLOW | 1 / 1 |
| Normal no order | NO_EFFECT | 0 / 0 | NO_EFFECT | 0 / 0 |
| Base omits Supplier A outstanding | DENY | 1 / 1 | DENY | 0 / 0 |
| Base reads SHIPPED as CANCELLED | DENY | 1 / 1 | DENY | 0 / 0 |
| Inventory base unit missing | DENY | 1 / 1 | DENY | 0 / 0 |
| Cancelled order has receipt | DENY | 1 / 1 | DENY | 0 / 0 |
| Base hard maximum corrupted | DENY | 1 / 1 | DENY | 0 / 0 |

`raw/order` means raw `place_order` call count / new external supplier-order
count. Detailed outcomes and timings are in `results-v2.json`.
