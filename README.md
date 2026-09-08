# SafeMA case-study repository

This repository keeps application evolution separate from SafeMA runtime
evolution. An application version owns its specification, natural-language
policy, Base App, and integration artifacts. A SafeMA version at the repository
root contains only reusable runtime code.

```text
apps/
  recommendation-submission/
    v1/
      app-spec-v1.md
      policy-v1.md
      base-app/
      safema-v1/                 # this app's SafeMA v1 models and evaluation
  multi-supplier-replenishment/
    v1/
      README.md
      design-history/
      app-spec-v1.md
      policy-v1.md
      base-app/
      safema-v2/                 # this app's SafeMA v2 integration
safema-v1/                       # shared SafeMA v1 runtime
safema-v2/                       # shared SafeMA v2 runtime
docs/                            # repository-wide research notes
app-1-recommendation-submission-one-pager.md
app-2-multi-supplier-replenishment-one-pager.md
```

## Versioning rule

- `apps/<name>/vN` is one frozen application/policy line.
- `safema-vN` is one shared runtime/model-language line.
- `apps/<name>/vN/safema-vM` contains only the adapter, executable models,
  mechanism tests, and evaluation for that application/runtime pairing.
- A new application version never overwrites an older frozen spec or policy.
- A new SafeMA version may coexist with the earlier runtime and may be applied
  to more than one application.

This layout permits, for example, application v1 and v2 to use SafeMA v1, or
application v1 to be evaluated with both SafeMA v1 and SafeMA v2.

## Current case studies

- [`recommendation-submission/v1`](apps/recommendation-submission/v1/README.md):
  completed first case study; its overview is also available as the root-level
  [`app-1-recommendation-submission-one-pager.md`](app-1-recommendation-submission-one-pager.md).
- [`multi-supplier-replenishment/v1`](apps/multi-supplier-replenishment/v1/README.md):
  completed second case study using shared SafeMA v2; its final overview is
  [`app-2-multi-supplier-replenishment-one-pager.md`](app-2-multi-supplier-replenishment-one-pager.md).
