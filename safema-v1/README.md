# SafeMA v1 prototype

This directory is deliberately outside `v1-impl/`. SafeMA patches configured
concrete effect APIs at runtime; the frozen Base App source remains unchanged.

## The three declarations

- `models/api-effects-v1.yaml`: how concrete Python calls become normalized
  effects (`DISCLOSE`, resources, destinations, channel).
- `models/trusted-origins-v1.yaml`: which successful calls may create trusted
  resource and destination metadata.
- `policies/same-principal-active-destination-v1.yaml`: the rule applied to the
  normalized effect and metadata.

Keeping effect interpretation separate from trust origins matters because a
sink describes where data is about to flow, while an origin describes who is
allowed to assert identity. They can evolve independently and neither is the
policy itself.

## Run the unchanged Base App under SafeMA

From the repository root, install the local package (or set `PYTHONPATH`):

```bash
python -m pip install -e ./safema-v1
python -m safema.recsub_runner \
  --metadata-db ./safema-sidecar.sqlite3 -- \
  --config ./v1-impl/examples/config.json daily-run
```

The arguments after `--` are the ordinary RecSub CLI arguments. Use the same
wrapper for `sync`, `register-letter`, and `process-pending`: trusted metadata
persists in the SafeMA sidecar across invocations. The Base App keeps owning
its own independent SQLite database.

## Verify

```bash
PYTHONPATH=safema-v1:v1-impl python -m pytest -q safema-v1/tests
PYTHONPATH=safema-v1:v1-impl python safema-v1/evaluation/run_v1.py
```

The evaluation writes deterministic machine-readable results to
`evaluation/results-v1.json` and a human-readable execution trace to
`evaluation/TRACE.md`.
