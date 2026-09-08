# Multi-Supplier Replenishment Automation — application v1

Current progress: `[■■■■■■■■■■] 10/10`

This directory owns the second case study's version-1 design history and,
after approval at the appropriate workflow steps, its frozen specification,
policy, Base App, and SafeMA integration artifacts.

The Step 1 application shape is recorded in
[`design-history/step-01-application-shape.md`](design-history/step-01-application-shape.md).

The approved Step 2 specification is frozen as
[`app-spec-v1.md`](app-spec-v1.md). Its decision notes are recorded in
[`design-history/step-02-specification-notes.md`](design-history/step-02-specification-notes.md).
Frozen-artifact hashes are tracked in
[`design-history/FROZEN-ARTIFACTS.md`](design-history/FROZEN-ARTIFACTS.md).

The approved Step 3 natural-language policy is frozen as
[`policy-v1.md`](policy-v1.md). Its preliminary enforceability classification
is recorded in
[`design-history/step-03-enforceability-classification.md`](design-history/step-03-enforceability-classification.md).

The Step 4 Base App implementation handoff is
[`CLAUDE-BASE-APP-HANDOFF.md`](CLAUDE-BASE-APP-HANDOFF.md). The delivered Base
App is isolated in `base-app/`.

The read-only Step 5 implementation inspection, exact effect boundary, test
evidence, and recorded discrepancies are in
[`design-history/step-05-base-app-audit.md`](design-history/step-05-base-app-audit.md).

The Step 6 architecture, trust boundary, effect normalization, trusted
outstanding resolver, numeric-policy decision, and relationship to traditional
taint tracking are recorded in
[`design-history/step-06-safema-architecture.md`](design-history/step-06-safema-architecture.md).

Steps 7–10 are recorded separately:

- [`design-history/step-07-executable-models.md`](design-history/step-07-executable-models.md)
- [`design-history/step-08-runtime-integration.md`](design-history/step-08-runtime-integration.md)
- [`design-history/step-09-mechanism-validation.md`](design-history/step-09-mechanism-validation.md)
- [`design-history/step-10-evaluation.md`](design-history/step-10-evaluation.md)

The completed App 2 integration, models, tests, and evaluation are in
[`safema-v2/`](safema-v2/README.md). The earlier
[`safema-v2-draft/`](safema-v2-draft/README.md) is preserved only as the
superseded meeting preview.

The final App 2 overview is available at the repository root as
[`app-2-multi-supplier-replenishment-one-pager.md`](../../../app-2-multi-supplier-replenishment-one-pager.md).

The frozen Base App remains independently runnable without SafeMA.
