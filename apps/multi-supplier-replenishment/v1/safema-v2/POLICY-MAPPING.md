# Step 7 — Natural-language policy to executable model mapping

Progress after executable model definition: `[■■■■■■■□□□] 7/10`

The complete owner policy remains `../policy-v1.md`. SafeMA v2 independently
enforces the subset that can be decided from the actual `PURCHASE` effect and
fresh authoritative state without replaying the Base App planner.

| Natural-language rule | SafeMA v2 status | Executable mechanism |
|---|---|---|
| Configured active SKU, approved supplier and mapping | Enforced | Registered supplier endpoint plus trusted `(supplier, supplier_sku) -> store_sku` mapping and active Inventory Ledger record |
| Configured destination/store | Enforced | Actual destination Context must equal owner destination authority and the inventory store |
| Positive integral quantity in `EACH` | Enforced | Strict Effect operand typing, `gt(quantity, 0)`, and trusted `base_unit == EACH` |
| Exact pack multiple | Enforced | `mod(quantity, pack_size) == 0` using the selected supplier's fresh offer |
| Quantity no greater than availability | Enforced | Numeric comparison with trusted current offer |
| Exact current offer price, USD | Enforced | Actual `expected_unit_price` equals trusted offer price; both currencies are USD |
| Unit-price, spend, and lead-time limits | Enforced | `lte` and exact `mul` against owner values and current offer |
| `on_hand + outstanding + proposed <= hard_max` | Enforced | Trusted resolver supplies identity-aligned on-hand/outstanding/hard-max; YAML applies exact `add` and `lte` |
| Missing, stale, incomplete, malformed, or contradictory required state blocks ordering | Enforced for modeled inputs | Resolver and model interpretation fail closed before the raw call |
| Receipt/order lifecycle interpretation | Enforced as trusted resolution | App-specific resolver independently validates both supplier snapshots and Inventory Ledger receipts |
| No fallback after definitive rejection | Base App only | This is multi-step application control flow, not one purchase authorization |
| Unknown outcome blocks retry/supplier switch | Not in v2 executable subset | Would require a second trusted lifecycle model keyed by idempotency attempt; deferred to avoid expanding the prototype |
| Exact forecasting and target calculation | Base App only | Would duplicate the complete deterministic planner at the sink |
| Globally correct supplier ranking | Base App only | Requires reconstructing all candidates and proving global choice quality |
| Scheduling/non-overlap | Base App only | Whole-application operational property |
| Complete operator records and reporting | Base App plus SafeMA audit | SafeMA records its own decision and raw-call status but does not prove Base App report completeness |
| No inventory mutation, cancellation, or unrelated order modification | Guaranteed only for discovered modeled effect surface | Step 5 found only `place_order`; unmodeled/bypass channels are outside the mediation guarantee |
| Base App cannot alter owner configuration or policy | Deployment assumption plus separation | SafeMA reads the owner file independently and pins its digest; OS/process isolation is outside this local prototype |

## Effect and trusted-state separation

- `api-effects-v2.yaml` contains only what the intercepted API is actually
  asked to do.
- `trusted-state-resolvers-v2.yaml` declares the live trusted resolution
  required for `PURCHASE`.
- `replenishment-purchase-v2.yaml` contains the authorization predicates.
- The resolver computes domain-specific outstanding quantity; the generic
  YAML interpreter performs transparent typed arithmetic and comparison.

These artifacts use the exact Base App API discovered in Step 5. They do not
change the Base App or place forecasting logic inside SafeMA.
