# Step 3 — Preliminary Enforceability Classification

Progress after drafting: `[■■■□□□□□□□] 3/10`

This table classifies the complete natural-language policy without changing
it. The classification is preliminary and does not choose an architecture.

| Policy rule | Likely independently enforceable? | Reason |
|---|---:|---|
| Only configured SKUs, approved suppliers, mapped supplier SKUs, and the configured destination | Yes | Actual purchase operands can be compared with trusted owner configuration. |
| Positive integer quantity, exact pack multiple, and no more than offered availability | Yes | Requires the actual quantity and a current authoritative offer. |
| Unit-price, per-order spend, currency, and lead-time limits | Yes | These are direct numeric comparisons using the offer, proposed order, and owner limits. |
| `on_hand + outstanding + proposed <= hard_max` | Likely yes | Requires trustworthy inventory, complete supplier-order state, receipt reconciliation, unit normalization, and numeric aggregation. |
| Unknown outcome blocks retry or supplier switching | Partly | Requires durable cross-call attempt state and authoritative idempotency-key reconciliation. |
| Missing, stale, malformed, or inconsistent required state prevents purchasing | Yes where observable | The decision can fail safely when a required trusted input is absent or invalid. |
| No inventory mutation, order cancellation, or modification of unrelated orders | Yes with boundary coverage | All consequential mutation channels would need to be identified and governed. |
| Exact 28-day forecast and supplier-specific target were calculated correctly | Not efficiently at the purchase boundary | Proving this requires replaying substantial planning logic and historical inputs. |
| The globally correct supplier was selected under the ranking procedure | Not efficiently at the purchase boundary | It requires reconstructing every candidate and proving no better candidate existed. |
| Scheduling, non-overlap, complete journaling, and operator-report quality | No, not as purchase authorization alone | These are whole-application operational obligations rather than properties of one proposed order. |
| The running application cannot modify owner configuration or policy | Partly | Purchase checks can distrust application claims, but write access and administrative integrity require separate controls. |

The likely executable subset should be selected only after the frozen Base App
exists and its actual external boundaries have been inspected.
