# Step 6 — SafeMA Architecture

Progress after architecture design: `[■■■■■■□□□□] 6/10`

Design date: 2026-09-04

This step starts from the frozen Base App and the exact effect boundary found
in Step 5. It does not change the Base App, freeze the meeting-draft YAML as an
executable model, or implement the runtime.

## 1. Architectural decision

SafeMA will remain an effect-boundary reference monitor rather than becoming a
second replenishment planner.

For the delivered application, it will mediate the one consequential external
operation:

```text
LocalSupplierService.place_order(
    supplier_sku,
    quantity,
    expected_unit_price,
    destination_id,
    idempotency_key,
)
```

Before invoking the original method, SafeMA will:

1. bind the receiver instance to a deployment-registered supplier endpoint;
2. normalize the actual call operands into one `PURCHASE` Effect;
3. resolve supplier SKU, store SKU, destination, inventory, outstanding
   orders, and owner limits from independently trusted sources;
4. reject missing, stale, incomplete, malformed, or contradictory state;
5. evaluate the executable purchasing constraints; and
6. call the raw supplier method only after `ALLOW`.

The key invariant is:

```text
trusted_on_hand(store_sku)
+ trusted_outstanding(store_sku)
+ actual_proposed_quantity
<= trusted_hard_max(store_sku)
```

SafeMA will not reproduce demand forecasting, pack planning, projected
stockout analysis, supplier ranking, scheduling, or report generation.

## 2. Trust boundary

### Trusted for authorization

- the SafeMA runtime, strict model loader, evaluator, and audit registry;
- deployment-approved Effect models, policy models, endpoint bindings, and
  resolver configuration;
- the owner-managed store, destination, approved supplier-SKU mappings, and
  hard maxima loaded independently of the Base App;
- Inventory Ledger state read through a SafeMA-owned resolver;
- complete order snapshots from both supplier systems read through
  SafeMA-owned resolvers;
- Inventory Ledger receipts used by the SafeMA outstanding-order resolver;
- the deployment-controlled clock used for snapshot freshness; and
- the binding between an intercepted supplier-service instance and its
  supplier endpoint identity.

Trusted data is still validated. “Trusted source” means authoritative for a
field, not that malformed, stale, or contradictory responses become valid.

### Untrusted for authorization

- all Base App planning, ranking, journal, decision, and cached state;
- any store SKU, on-hand, outstanding, hard maximum, or supplier identity
  claimed by Base App internals;
- the store SKU embedded in the idempotency-key text;
- Base App logs and previously computed candidates;
- receiver fields that have not been bound by the trusted deployment; and
- raw strings or numeric values merely because they came from a Python type
  annotation.

The actual supplier SKU, destination, quantity, price, and idempotency key are
not “trusted facts.” They are actual Effect operands: the values the external
API is about to receive. Policy must judge them, not believe them.

### Deployment assumption

This local prototype protects against application mistakes and injected bad
application state, not a hostile process with arbitrary Python-memory or
filesystem write access. The experiment harness controls model files, trusted
world files, endpoint registration, and the SafeMA sidecar. A production
deployment would need OS/process isolation or service-side mediation to defend
those assets from a malicious application process.

## 3. Effect interception and normalization

The current Base App uses the same Python class for Supplier A and Supplier B.
The method's receiver therefore matters. Reading
`receiver.supplier_id` directly would turn a mutable Base App-visible field
into authorization metadata. Instead, the SafeMA bootstrap will register each
approved service instance against a deployment-known supplier identity.

At interception time:

```text
registered receiver identity  -> supplier_id
actual supplier_sku argument  -> Resource identity
actual destination_id         -> Context identity
actual quantity               -> proposed_quantity
actual expected_unit_price    -> expected_unit_price
actual idempotency_key        -> idempotency_key
```

An unregistered or ambiguously registered receiver fails closed. The
normalized Effect is:

```text
PURCHASE(
  resources  = [supplier_sku],
  contexts   = [delivery_destination],
  attributes = {
    supplier_id,
    proposed_quantity,
    expected_unit_price,
    idempotency_key,
    currency = USD
  }
)
```

Python signature binding recovers named operands even though the Base App
currently calls the method positionally. Missing, extra, Boolean-as-integer,
non-integral quantity, invalid Decimal, or otherwise uninterpretable operands
cause `DENY` before the raw call.

## 4. Resource identity resolution

SafeMA must not derive a store SKU by parsing display names, supplier-SKU text,
or the idempotency key. It performs the following trusted joins:

```text
(registered supplier_id, actual supplier_sku)
    -> owner-approved supplier mapping
    -> store_sku

actual destination_id
    -> owner destination authority
    -> store_id

(store_id, store_sku)
    -> Inventory Ledger record and receipt state
```

The resolved inventory record must have exactly the configured store and SKU,
be active, use `EACH`, and carry a non-negative integer `on_hand`. Ambiguous or
missing mappings deny. No unit conversion is performed in v1 of this app.

## 5. Trusted outstanding-order resolver

Outstanding quantity is not accepted from the Base App. Immediately before a
purchase decision, a SafeMA-owned application resolver will:

1. read fresh complete order snapshots for the configured destination from
   both approved supplier endpoints;
2. require supplier and destination identities to agree with those endpoints;
3. map every relevant supplier SKU through owner-controlled mappings;
4. fetch Inventory Ledger receipts for every returned order ID, including
   `CANCELLED` orders so that the Step 5 blind spot is not repeated;
5. reject duplicate, partial, cancelled-order, wrong-store, wrong-supplier,
   wrong-SKU, or wrong-quantity receipt relationships;
6. count full quantities for `ACCEPTED`, `SHIPPED`, and unreceipted
   `DELIVERED` orders;
7. count zero for validly received and `CANCELLED` orders; and
8. sum the result across both suppliers for the resolved store SKU.

The Inventory Ledger and supplier snapshots must not be future-dated or more
than 15 minutes old. Missing completeness evidence is failure, not `true`.
Missing base-unit evidence is failure, not `EACH`.

The lifecycle interpretation above is application-specific trusted resolver
logic. It does not belong as hard-coded knowledge in the generic SafeMA core.

## 6. Where numeric aggregation belongs

The final bounded arithmetic belongs naturally in the generic policy model:

```text
add(on_hand, outstanding, proposed_quantity) <= hard_max
```

The reasons are:

- all operands are already typed, identity-aligned authorization values;
- addition and ordered comparison are small deterministic operators;
- the same operators are reusable for budgets, quotas, storage limits, and
  cumulative resource exposure; and
- leaving the final sum inside an opaque resolver would hide the actual owner
  rule from the policy artifact.

The generic model should therefore gain strict `add`, `gt`, `gte`, `lt`, and
`lte` operators over exact integers and Decimals. It must reject mixed or
unsupported types rather than perform Python coercion, string concatenation,
or binary floating-point conversion.

By contrast, deciding whether a `DELIVERED` order remains outstanding, joining
receipts, and rejecting lifecycle contradictions are domain semantics. Those
belong in the application-specific trusted resolver. Forecasting and supplier
ranking remain exclusively Base App responsibilities.

## 7. Metadata and sidecar state

The sidecar stores:

- trusted endpoint-instance bindings;
- the owner configuration version or digest used for a decision;
- Effect, resolved resource identities, authoritative snapshot identifiers,
  individual numeric operands, policy result, and raw-call status; and
- any later model-declared cross-call enforcement state.

Dynamic on-hand and outstanding values should be resolved live for each
effect, not treated as durable cached authorization. They may be copied into
the immutable decision audit record after resolution.

The hard-maximum check requires no reservation table in this frozen
single-worker/local-world application. The guarantee assumes no concurrent
external purchaser changes exposure between resolution and the raw call. A
production multi-writer system would require a versioned conditional write or
reservation protocol, but introducing one here would contradict the frozen
single-worker scope.

## 8. Responsibilities

| Component | Responsibility |
|---|---|
| Base App | Forecast demand, form candidates, rank suppliers, schedule runs, commit its attempt, call supplier API, and report its result |
| SafeMA core | Intercept modeled effects, bind actual arguments, invoke trusted resolvers, evaluate generic policy operators, fail closed, and audit before/after raw invocation |
| App 2 SafeMA resolver | Resolve store/SKU identities, validate snapshots and units, reconcile receipts with both suppliers' order lifecycles, and expose typed `on_hand` and `outstanding` |
| Owner/deployment | Approve supplier endpoints, destination, mappings, hard maxima, models, and trusted source configuration |
| Inventory Ledger | Authoritative on-hand, active/unit state, and receipts |
| Supplier services | Authoritative offers, order state, idempotency lookup, and raw purchase effect |

SafeMA authorizes the Effect; it does not tell the Base App what it should have
forecast or which supplier it should have preferred.

## 9. Denial behavior without Base App modification

The current shared runtime raises `SafeMADenied`. App 2's
`place_purchase_order` catches only Base App `ExternalServiceError`; an
untranslated exception would leave a durably committed attempt in
`DISPATCHING`, later recover it as unknown, and interrupt normal run handling.

The App 2 integration layer must therefore translate a pre-call SafeMA denial
into the supplier protocol's definitive no-order result:

```text
OrderRejected(code="SAFEMA_POLICY_DENIED", message=<decision reference>)
```

This is accurate with respect to the crucial supplier contract: the wrapper
did not invoke the raw service, so no order exists. The Base App remains
unchanged and records a rejected attempt. The SafeMA audit retains the more
precise fact that the mediator, not the remote supplier, denied it. Model or
resolver failures also fail before the raw call; their adapter-facing result
must preserve definitive non-invocation rather than masquerade as an uncertain
post-dispatch timeout.

The denial translation is application-adapter glue, not a purchasing concept
inside the generic core.

## 10. Executable-policy boundary

The natural-language policy remains the complete owner policy. Step 7 should
map each rule explicitly. The intended architecture supports independent
enforcement of at least:

- registered supplier endpoint, configured destination, configured active SKU,
  and approved supplier mapping;
- positive integral quantity and `EACH` unit;
- fresh offer identity, pack, availability, price, currency, lead time, and
  owner price/spend/lead limits;
- fresh complete inventory/order/receipt state;
- `on_hand + outstanding + proposed <= hard_max`; and
- potentially unresolved-attempt/idempotency blocking, if the later model adds
  the necessary trusted cross-call lifecycle.

SafeMA will not independently enforce:

- exact 28-day exponential-smoothing correctness;
- the supplier-specific replenishment target;
- globally optimal supplier ranking;
- scheduler uniqueness and non-overlap;
- complete Base App journaling or report quality; or
- the prohibition on unrelated mutation channels beyond the one effect API
  found in the frozen Base App.

These remain application obligations and evaluation dimensions rather than
claims of the purchase-boundary authorization mechanism.

## 11. Relationship to source/sink/propagation and taint

SafeMA has clear origins and sinks, but it deliberately does not implement
traditional whole-program taint propagation.

| Concept | Traditional dynamic taint | SafeMA |
|---|---|---|
| Source | Marks sensitive or untrusted runtime values | Declares trusted metadata origins and independently resolved authoritative state |
| Propagation | Copies/combines labels through assignments, calls, containers, and transformations | No general label propagation; reconstructs the actual Effect at the sink and binds its resource identities to trusted metadata |
| Sink | Checks a labeled value when it reaches a dangerous API | Intercepts the modeled effectful API before its raw body |
| Decision | Usually asks whether a prohibited flow reached the sink | Evaluates an authorization predicate over actual Effect operands plus current trusted state |

For Recommendation Submission, the sensitive source can be described as the
actual registered letter and the sink as `email.send` or `portal.submit`.
SafeMA does not follow a taint bit from file-open through every Base App
operation. At the sink it hashes the actual attachment and rebinds that
identity to trusted applicant/request metadata. This enforces an endpoint
information-flow relation without whole-program propagation tracking.

For Replenishment, forcing the policy into a taint vocabulary is even less
natural. Inventory, order, and owner configuration services are authoritative
state sources; `place_order` is the sink; but the central policy is a stateful
numeric authorization invariant, not “tainted data must not flow.” SafeMA
re-reads those sources at the sink and combines them with the actual proposed
quantity.

The accurate description is therefore:

> SafeMA is a model-driven, provenance-aware reference monitor with sink-time
> identity reconstruction and trusted-state resolution. It can enforce some
> information-flow policies, but it is not a traditional taint tracker.

Calling identity resolution “propagation” would obscure the implementation.
It is better to state that SafeMA avoids propagation when stable resource
identity can be reconstructed at the consequential boundary.

## 12. Difference from the Recommendation Submission case

Both cases use the same core pattern:

```text
actual API call -> normalized Effect -> trusted metadata -> policy -> raw API
```

Recommendation Submission primarily tests resource identity, destination
authority, and trusted Context lifecycle. Its letter identity can be recovered
by hashing an actual file operand, and its policy uses equality, subset, and
quantification.

Replenishment adds:

- two instances of one effect API whose receiver must be bound to endpoint
  identity;
- live multi-service state resolution at the instant of purchase;
- supplier-SKU to store-SKU normalization;
- order/receipt lifecycle reconciliation across two suppliers;
- exact typed numeric aggregation and comparison; and
- an adapter-specific denial translation that preserves the frozen Base App's
  expected return protocol.

This extends SafeMA from identity-based disclosure control to a stateful
resource-exposure constraint without turning SafeMA into an application
planner.

## 13. Step boundary

This completes architecture design only. The meeting-draft YAML remains a
preview. Step 7 must revise it to the architecture above, define the trusted
origin/resolver artifacts, and provide the complete natural-language-to-
executable-policy mapping before any model is called executable.
