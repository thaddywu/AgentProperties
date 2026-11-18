# Setup and verification

From the repository root:

```bash
./install.sh
source .venv/bin/activate
```

The installer needs Python 3.10+ and a running Docker daemon accessible to your
user. Automatic setup currently targets Linux x86_64 with Ubuntu/Debian package
tools. It requests `sudo` only for missing system packages, prepares the native
engine and both coding CLIs, builds the execution images and runs engine checks.
Existing compatible tools are reused; repeated builds use Docker's layer cache.
It never reads or writes model credentials. `--provider openai`, `anthropic`,
`codex-compatible-local-endpoint` or `none` limits optional coding-CLI preparation;
the local option prepares Codex and the default `both` prepares both CLIs.

## Optional: manual installation

If the installer stops, complete the missing steps below. System-package commands
are for Ubuntu 22.04+; other systems need equivalent packages. Use the original
application's Phase 1 setup for its own dependencies.
Without `sudo`, use tools already provided by your environment or ask an
administrator to install missing system packages and enable Docker access.

### Python, Git and system libraries

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv git curl ca-certificates \
  dpkg util-linux libffi8 libgomp1 libncurses6 libtinfo6 libsqlite3-0 \
  libstdc++6 libgcc-s1 zlib1g
```

### Docker

If Docker is absent:

```bash
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in, then run `docker info`. Existing Docker Desktop or rootless
installations can be used directly once that command succeeds.

### Framework

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp]'
```

### Soufflé 2.5

```bash
POLICY_ENGINE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/policyweave/souffle"
python -m policyweave.adapters.install_souffle --directory "$POLICY_ENGINE_DIR"
export PATH="$POLICY_ENGINE_DIR/usr/bin:$PATH"
souffle --version
```

`prlimit` is supplied by `util-linux` in the first step. Keep the engine directory
on `PATH` when starting the ported application or Inspector queries.

### Coding CLI

Install the native CLI for the selected provider. OpenAI:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh -o /tmp/install-codex.sh
sh /tmp/install-codex.sh
export PATH="$HOME/.local/bin:$PATH"
codex --version
```

Anthropic:

```bash
curl -fsSL https://claude.ai/install.sh -o /tmp/install-claude.sh
bash /tmp/install-claude.sh 2.1.252
export PATH="$HOME/.local/bin:$PATH"
claude --version
```

These are the [Codex native installer](https://learn.chatgpt.com/docs/codex/cli)
and [Claude Code native installer](https://code.claude.com/docs/en/setup).
The automatic installer instead uses checksum-pinned native releases and checks
the flags required by the isolated coding sessions. No CLI login is needed for
PolicyWeave's model relay; configure the shared YAML separately.

### Execution images

```bash
docker build -f src/policyweave/adapters/Dockerfile -t policy-portin:local .
docker build -f src/policyweave/adapters/Dockerfile.batch -t policy-portin:batch-v1 .
docker run --rm --network none policy-portin:local
```

Docker isolates translation and its offline verification. Scenario experiments
run in the application's own environment. Application-specific dependencies used
by container checks must also be available in the selected verification image;
host Python packages are not automatically inherited by containers.

## Development verification

Use Python 3.10 or newer. The execution adapter targets Linux; its native runner needs `prlimit` and the libraries used by Soufflé. The review UI and structural tests can run without the engine.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[mcp,test]'
python -m playwright install chromium
```

The `mcp` extra is needed only for MCP registration and its conformance tests. The `test` extra installs headless browser tools. Installation includes PyYAML for private connection files; the core imports no vendor SDK.

On Linux x86_64, the following helper downloads the pinned Ubuntu 22.04 Soufflé 2.5 package, verifies its SHA-512 and extracts it without root:

```bash
POLICY_ENGINE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/policyweave/souffle"
python -B -m policyweave.adapters.install_souffle --directory "$POLICY_ENGINE_DIR"
export PATH="$POLICY_ENGINE_DIR/usr/bin:$PATH"
souffle --version
python -B -m tests
```

Full offline verification requires both `souffle` and `prlimit` on `PATH`; some native tests skip when they are absent, while others fail. A skipped test is not execution validation. CI supplies both and tests the installed distribution outside the checkout.

```bash
python tests/workbench/ui_smoke.py
python tests/workbench/codex_ui_smoke.py
python tests/workbench/student_ui_smoke.py
```

Browser checks use synthetic model output, launch headless Chromium and save artifacts under `~/.cache/policyweave/test-results/`, respecting `XDG_CACHE_HOME`. They require no model account, desktop windows or host workspace.

The review server stores private state under `~/.local/state/policyweave/default`, respecting `XDG_STATE_HOME`; `--data` can select an explicit location. To reopen an existing PolicyScope study, pass its original directory with `--data`. Existing trajectory files remain readable. Generated documents and Ruff caches also live outside the checkout. Python's own bytecode cache can be redirected during development:

```bash
export PYTHONPYCACHEPREFIX="${XDG_CACHE_HOME:-$HOME/.cache}/policyweave/pycache"
```

Install once to use `policyweave --help` and each module's `--help`. Individual entry points include `policy-add`, `policy-translate`, `policy-backtranslate`, `policy-review`, `policy-enforce` and `policy-analyze`.

Model connections use private YAML through `--connection`. Copy
`examples/connection.yaml` outside the repository and fill the `openai` or
`anthropic` key. `provider: auto` prefers OpenAI when both keys are filled;
`provider: anthropic` selects Claude explicitly. The selected provider's coding
CLI is needed for app porting and repository reading, while inspection and
data-only model calls do not need one. The [connection guide](porting.md) lists
defaults, supported CLI boundaries and the optional local-fixture Docker check.
No provider-specific environment setup is required.
For local or self-hosted models, select `provider: codex-compatible-local-endpoint`
and fill that section's `baseUrl` and `modelId`; `apiKey` may be empty. This option
requires explicit selection and does not inherit hosted defaults. See
[local endpoint requirements](porting.md#local-model-endpoints).

Start Inspector with that connection file for trajectory review and QA:

```bash
policyweave inspect --traj trajectory.jsonl --connection /path/to/private-connection.yaml
```

Use the same YAML for translation and Inspector. The trajectory may also be JSON;
Open/upload remains available after startup.
