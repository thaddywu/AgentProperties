# Multi-Supplier Replenishment v1 — SafeMA v2 integration

Progress: `[■■■■■■■■■■] 10/10`

This integration mediates the frozen Base App without modifying it. It maps
the actual supplier `place_order` call into a `PURCHASE` Effect, independently
resolves current authoritative purchasing state, evaluates executable YAML,
and calls the raw supplier method only after `ALLOW`.

The reusable application-agnostic runtime is at the repository root in
`safema-v2/`. App-specific trusted state, denial translation, models, tests,
and evaluation remain in this directory.

## Contents

- `models/api-effects-v2.yaml`: concrete API to `PURCHASE` normalization;
- `models/trusted-state-resolvers-v2.yaml`: required live trusted resolution;
- `models/trusted-origins-v2.yaml`: no event-driven origins are needed here;
- `policies/replenishment-purchase-v2.yaml`: executable purchasing policy;
- `POLICY-MAPPING.md`: complete natural-language-to-executable mapping;
- `replenishment_safema/trusted_state.py`: strict independent resolver;
- `replenishment_safema/integration.py`: runtime installation, endpoint
  binding, and denial-result translation;
- `runner.py`: one-run SafeMA entry point;
- `tests/`: mechanism validation; and
- `evaluation/`: baseline/treatment harness and results.

## Enforcement path

```text
Base App selected_supplier.place_order(actual operands)
  -> SafeMA wrapper
  -> registered receiver binding
  -> PURCHASE Effect
  -> trusted owner/inventory/order/receipt/offer resolution
  -> YAML predicates
  -> ALLOW -> raw supplier method -> external order
  -> DENY  -> OrderRejected(SAFEMA_POLICY_DENIED), no raw call
```

The core ceiling predicate is:

```text
trusted_on_hand + trusted_outstanding + actual_quantity <= trusted_hard_max
```

The policy also verifies destination and supplier-SKU identity, active `EACH`
inventory, positive pack-aligned quantity, availability, exact current USD
price, and owner price/spend/lead-time limits.

## Run tests

From the repository root:

```bash
PYTHONPATH=safema-v2 \
  python -m pytest -q safema-v2/tests

PYTHONPATH=safema-v2:apps/multi-supplier-replenishment/v1/base-app/src:apps/multi-supplier-replenishment/v1/base-app:apps/multi-supplier-replenishment/v1/safema-v2 \
  python -m pytest -q apps/multi-supplier-replenishment/v1/safema-v2/tests
```

Expected results are 4 shared-runtime tests and 24 App 2 mechanism tests.

## Run the Safe App

The config must point to an initialized local world. Then run:

```bash
PYTHONPATH=safema-v2:apps/multi-supplier-replenishment/v1/base-app/src:apps/multi-supplier-replenishment/v1/safema-v2 \
  python apps/multi-supplier-replenishment/v1/safema-v2/runner.py \
    --config /path/to/config.json \
    --metadata-db /path/to/safema.sqlite3 \
    --json
```

The output contains both the unchanged Base App run report and SafeMA decision
records, including whether each raw effect was invoked.

## Evaluation result

Across seven paired scenarios:

- policy-violating effects reaching raw API: baseline `5`, treatment `0`;
- legitimate workflows completed: baseline `2/2`, treatment `2/2`;
- false denials: `0`;
- raw purchase calls: baseline `6`, treatment `1`.

See `evaluation/TRACE.md` and `evaluation/results-v2.json` for exact cases.
