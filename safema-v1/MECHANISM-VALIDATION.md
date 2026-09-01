# Stage 9 mechanism validation

The tests in `tests/test_runtime.py` validate the instrumentation mechanism,
not merely the Base App's native policy:

- concrete email and portal methods are mediated before their raw bodies;
- signature-bound arguments are normalized according to YAML selectors;
- trusted registration and request-source returns populate a separate SQLite
  sidecar;
- resource resolution binds both canonical path and SHA-256 content version;
- missing metadata, changed file content, and unauthorized destinations deny
  closed;
- denied effects leave recording adapters with zero calls;
- valid email, portal, and no-attachment reminder calls still reach raw APIs;
- request cancellation deactivates its destination context;
- the external runner preserves sidecar metadata across separate `sync`,
  `register-letter`, and `process` CLI processes;
- baseline fault injection demonstrates that the tested denials come from
  SafeMA rather than the Base App's own guard.

Run with:

```bash
PYTHONPATH=safema-v1:v1-impl python -m pytest -q safema-v1/tests
```
