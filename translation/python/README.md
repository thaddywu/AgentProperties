# Independent translation layer

`policy_translation.translate(source, binding, generate, ...)` returns a pinned
review draft. `generate(stage, prompt)` is the optional model boundary. The package
imports only the standalone policy engine and the Python standard library.

Stages are requirement decomposition, shared-rule generation and back-translation.
Each stage allows one validation correction, with a record callback retaining the
exact prompts, responses and failures. Transport failures do not retry or substitute
a reference. Requirements-only results are explicit when no rule target exists.

Source text stays unchanged; requirements quote unique spans using Unicode code-point
offsets. Any omitted text becomes an unresolved item. Shared rule IDs preserve
many-to-many mappings. Rule syntax, schema, ownership, safety and stratification
are checked by the same engine used for execution. This is static validation,
not semantic equivalence or adapter validation.

Acceptance tests are excluded from model context. Back-translation receives only
actual rules, predicate meanings, configuration, foundations and runtime semantics;
it receives neither source policy nor distilled statements. App-specific effects
and evidence producers remain explicit obligations. The translator cannot install
policies, approve itself or modify the trusted vocabulary.

Install with the runtime, or use the checkout import paths:

```bash
PYTHONPATH=runtime/python:translation/python python3 -m policy_translation \
  /path/to/policy.txt --binding /path/to/runtime.json \
  --connection /path/to/private-connection.json \
  --output translation/output/new-review
```

A new private output directory contains attempts, review and measured usage. See
[model connections](../../evaluation/README.md#model-connection) for the optional
standard compatible adapter. Other providers implement the same generate callable;
SDK dependencies belong in adapters, not the pipeline.

This is the student-review path. It does not replace the historical TS developer
approval/bundle CLI, expand arbitrary predicates, parse PDF/Word, or generate adapters.
Independent application acceptance tests should run before any candidate is loaded.
