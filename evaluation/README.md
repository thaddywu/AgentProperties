# Evaluation cases

`examples/` contains synthetic data-only inputs for the installed runner:

```bash
policyscope run-cases --cases evaluation/examples/document-tests.json --data output/example
```

The application runner owns reset, real callbacks and authoritative observations. A recorded expected outcome is a claim for human assessment, not an oracle derived from the generated policy. See [the study protocol](../docs/study.md).

Private run records go under ignored `output/`. Historical public results and aggregate experiment metrics are indexed in [the archives](../docs/archives.md). Evaluation is not a sixth policy module; HTTP/study composition lives in `src/policyscope/workbench/`.
