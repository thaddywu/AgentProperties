# Setup and verification

Use Python 3.10 or newer. The execution adapter targets Linux; its native runner needs `prlimit` and the libraries used by Soufflé. The review UI and structural tests can run without the engine.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[mcp,test]'
python -m playwright install chromium
```

The `mcp` extra is needed only for MCP registration and its conformance tests. The `test` extra installs headless browser tools. The base distribution has no Python runtime dependencies.

On Linux x86_64, the following helper downloads the pinned Ubuntu 22.04 Soufflé 2.5 package, verifies its SHA-512 and extracts it without root:

```bash
python scripts/install_souffle.py --directory .tools/souffle
export PATH="$PWD/.tools/souffle/usr/bin:$PATH"
souffle --version
python scripts/check.py
```

Native tests explicitly skip when the engine or `prlimit` is absent; a skipped test is not execution validation. CI supplies both and tests the installed distribution outside the checkout.

```bash
python tests/workbench/ui_smoke.py
python tests/workbench/codex_ui_smoke.py
python tests/workbench/student_ui_smoke.py
```

Browser checks use synthetic model output, launch headless Chromium and save ignored artifacts under `test-results/`. They require no model account, desktop windows or host workspace.

Install once to use `policyscope --help` and each module's `--help`. Individual entry points include `policy-add`, `policy-translate`, `policy-backtranslate`, `policy-review`, `policy-enforce` and `policy-analyze`.
