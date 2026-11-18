# Comparison cases

These fictional JSON files are data-only inputs for a trusted application runner:

```bash
policyweave run-cases --cases examples/cases/document-tests.json --data ../policyweave-runs/example
```

The application owns setup validation, reset, callbacks and authoritative observations. An expected outcome is a human assessment target, not an oracle generated from the policy. Choose a private result directory outside the source checkout.

See [repository history](../../docs/repository-structure.md#historical-implementations) for archived implementations and results.
