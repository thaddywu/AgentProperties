# Contributing

Install the root Python distribution and read [the module boundaries](../docs/repository-structure.md).

```bash
python -m pip install -e '.[mcp,test]'
python -B -m tests
python -m playwright install chromium
python tests/workbench/ui_smoke.py
python tests/workbench/codex_ui_smoke.py
python tests/workbench/student_ui_smoke.py
```

Native checks need Soufflé and `prlimit`; [setup](../docs/setup.md) provides the pinned engine helper. Tests are deterministic and offline. Browser checks are headless. Keep model/vendor code in adapters, application facts/effects in app adapters and shared rule semantics in `core`.

Never commit credentials, private endpoints, production data or raw private experiment outputs. Use fictional fixtures. Keep `master` focused on active Python modules; the five `archive/*` branches are frozen references. Explain product behavior and validation in public-safe words. UI changes must include a CI screenshot showing the changed screen.
