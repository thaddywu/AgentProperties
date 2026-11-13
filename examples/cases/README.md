# Comparison cases

These fictional JSON files are data-only inputs for a trusted application runner:

```bash
policyscope run-cases --cases examples/cases/document-tests.json --data ../policyscope-runs/example
```

The application owns setup validation, reset, callbacks and authoritative observations. The LabCluster file additionally requires its separately validated port and runner. An expected outcome is a human assessment target, not an oracle generated from the policy. Choose a private result directory outside the source checkout.

See the [study protocol](../../docs/study/protocol.md) for judgments and limitations, or [archives](../../docs/archives.md) for historical results.
