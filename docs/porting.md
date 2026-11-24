# Application porting

The generic rule translator accepts an existing trusted binding. The optional
application-port adapter discovers source boundaries, freezes a binding, generates
rules, then instruments and tests original callbacks. Independent reverse reading
and alignment are later entries. These are different entry points.

The [EDB and translation design](design/observations-and-translation.md) defines what
input observations mean and which writes belong to the host or an authorized
agent. The [staged workflow](design/port-pipeline.md) specifies discovery, a frozen binding,
rule compilation, per-call instrumentation, agent recording authority, execution
and independent review. The current harness enforces four host stages:
data-only discovery, data-only binding planning, rules-only generation and
instrumentation with verification. Agent recording authority belongs to the
binding plan and instrumentation; reverse reading/alignment remain separate.
`CodexPort.translate` stops after verification. The adapter CLI can explicitly
compose later review steps with `--stage all`.

Inventory and binding call `CodexPort.plan()` through the provider-neutral model
connection with strict JSON schemas and a bounded source bundle. These stages
have no file tools or app execution. The coding CLI is used for rules and
instrumentation; host validators check every planning response before progression.

```bash
RUN_DIR="$(policyweave new-run Draft)"
policy-translate /path/to/policy.md --binding /path/to/runtime.json \
  --connection /path/to/private-connection.yaml --output "$RUN_DIR/translation"
```

The optional application-port workflow requires Docker, Linux x86_64 and a
standalone coding CLI: Codex for the default connection protocol, or the native
Claude Code executable for `messages`. Build its isolated execution images:

```bash
docker build -f src/policyweave/adapters/Dockerfile -t policy-portin:local .
docker build -f src/policyweave/adapters/Dockerfile.batch -t policy-portin:batch-v1 .
```

Translate and review:

```bash
policyweave port --input "$ORIGINAL_APP_DIR" --output "$PORTED_APP_DIR" \
  --connection "$CONNECTION_FILE"
policyweave view-translation \
  --back-translation "$PORTED_APP_DIR/back-translation" \
  --policy "$ORIGINAL_APP_DIR/policy.md"
```

The original app is a clean Git checkout with `app.md` and `policy.md`. The target must be absent or empty. Debug flags can select existing document names without rewriting them. Git branches remain user-owned. The adapter preserves original documents, tests and business behavior; it adds rules, mediation and explicit fact producers. Passing development tests does not prove full policy fidelity or complete mediation.

From the repository root, `RUN_DIR="$(policyweave new-run APP)"` creates a fresh
`runs/YYYYMonDD_HHMM_APP/` workspace, with a numeric suffix for same-minute runs.
Keep `orig_app/`, `ported_app/`, harnesses, results, reports and cost records inside
that workspace. The entire `runs/` tree is ignored by Git and Docker builds.
Generated harness paths are relative to the harness location, so keep the complete
workspace layout when moving it. See [the demo walkthrough](../demo/step_by_step.sh).

The execution image supplies framework dependencies. If an application needs
additional or incompatible dependencies, prepare its test image before porting
and select it with `--image IMAGE`. The coding container has no package-install
or general network access. Use the same application dependencies when running
the original and generated harnesses.

Installation registers the `policyweave` command; no account registration is
required. Missing `app.md` or `policy.md` fails before model calls. A nonempty
output fails without replacing its contents; missing output parents are created.
The original checkout remains unchanged. The published app omits authoring policy
documents and retains runtime prompts separately where needed.

`port` defaults to verification, independent reading and source alignment. Use
`--no-back-trans` to publish only the verified implementation, then run:

```bash
policyweave back-translate --ported-app /path/to/ported-app \
  --policy /path/to/original-app/policy.md \
  --output /path/to/back-trans \
  --connection /path/to/private-connection.yaml
policyweave review --policy /path/to/original-app/policy.md \
  --back-translation /path/to/back-trans
```

The independent reading receives implementation evidence without the source
policy, runner, tests or forward plans. Only the subsequent alignment pass reads
the original policy. An explicit new reading uses new empty output and private
work directories; it cannot overwrite an earlier reading. `--work-dir` selects
private evidence outside the app and review bundle. By default a sibling hidden
work directory retains attempts, including failures. `back-translate` does not
execute or re-port the app.

Both paths produce a fixed review contract:

```text
back-trans/                    # port's default: PORTED/back-translation/
  execution.json               # frozen independent checks and limitations
  alignment.json               # source sentence → check IDs
  manifest.json                # policy hash, implementation and asset hashes
  description.md               # human-readable reading, when available
```

`review --policy` also requires the bundle to compare against. It rejects a
different policy or changed pinned implementation. Judgments default to
`back-trans/../review.json`; `--review-file` selects a separate submission path.
Review never runs the application. `review` and `view-translation` open the same
panel. The `backtranslate` entry accepts JSON evidence input.

A port needs actual tool/message/model-context/final-reply/background boundaries,
not just an inventory of tool names. Fix real parameters, field meanings, units,
cardinalities, keys, scopes and producers before generating rules. Preserve exact
source evidence for the binding, and report missing confirmations or observations
as gaps. Supervising the coding agent's own tools does not establish mediation of
the target app's effects.

Accepted `inventory.json` and `binding-plan.json` lead to a hashed
`binding-freeze.json` and host-generated `policy_port/binding.py` factory. The
factory pins shared EDB and observation/call contracts. Each planned call has
`role: gate` or `role: producer`: gates require native decision evidence,
while observation producers require actual source execution and recording.
Older plans without a role retain the gate requirement. Rules use the existing
schemas and must pass bounded native initialization before freezing for
instrumentation. `workflow.json` records stage progression and failures; later changes to
frozen artifacts are rejected. Source quotations and Python signatures establish
provenance and structural consistency, not semantic correctness of every mapping
or complete mediation. Static checks do not prove arbitrary Python helpers safe.

A model-driven port uses a real model for coding-agent stages. Its deterministic
native callback tests may use labeled fixtures for external dependencies; that
does not claim execution of the target app's own LLM scenarios. App-agent task
completion requires separate evidence from its original native workflow.

Connection files use YAML only (`.yaml` or `.yml`). Copy the public
[empty-key template](../examples/connection.yaml) to a private location outside
the repository and fill either key:

```yaml
provider: auto

openai:
  apiKey: ""
  modelId: gpt-6.1-sol
  reasoningEffort: medium

anthropic:
  apiKey: ""
  modelId: claude-opus-5-5
  reasoningEffort: medium

codex-compatible-local-endpoint:
  baseUrl: ""
  modelId: ""
  apiKey: ""
  reasoningEffort: null
```

`provider` may be `auto` (also the default when omitted), `openai`, `anthropic`
or `codex-compatible-local-endpoint`. Auto selects a hosted section with a
nonblank key; if both hosted keys are filled, it selects OpenAI. The local option
always requires explicit selection, even with a key. Blank or omitted sections
are inactive. Explicit selection requires that
section's key or an explicit `baseUrl` for a keyless endpoint, and never falls
back to the other section. An empty template fails
with an instruction to fill one key. JSON connection files and flat connection
documents are rejected. Artifact and trajectory JSON formats are unchanged.

All CLI entries use the same loader and select once per invocation. Only the
selected section is passed to the model and coding adapters; the other key is
discarded. OpenAI selects Chat Completions for data-only calls and Codex/Responses
for coding sessions. Anthropic selects native Messages and Claude Code. The
local option reuses Chat Completions and Codex/Responses, with no hosted endpoint,
model ID or reasoning-effort defaults. Both `baseUrl` and `modelId` are required.
The corresponding CLI must be installed for coding sessions; selection does not
change based on installed executables or retry against another provider.

| Section default | OpenAI | Anthropic | Codex-compatible local endpoint |
| --- | --- | --- | --- |
| `baseUrl` | `https://api.openai.com/v1` | `https://api.anthropic.com/v1` | Required |
| `modelId` | `gpt-6.1-sol` | `claude-opus-5-5` | Required |
| `reasoningEffort` | `medium` | `medium` | Omitted unless configured |
| Coding executable | `codex` | `claude` | `codex` |

The template pre-fills model IDs for visibility; those same defaults apply if the
fields are omitted. Students ordinarily fill only one `apiKey`. Advanced fields
stay inside the corresponding section: `baseUrl`, `modelId`, `reasoningEffort`,
`maxTokens`, `timeoutSeconds`, `codingCommand` and `headers`. Ordinary data-only
calls default to 12,000 tokens and 180 seconds; port planning defaults to 128,000
tokens and 1,800 seconds unless explicitly configured. A custom endpoint can reuse
either protocol. For a keyless local connection, explicitly select its section
with `provider` and set `baseUrl` and `modelId`.

### Local model endpoints

Local or self-hosted models use the same connection YAML. Select the dedicated
option for a service compatible with Codex:

```yaml
provider: codex-compatible-local-endpoint
codex-compatible-local-endpoint:
  baseUrl: http://127.0.0.1:8000/v1
  modelId: local-model
  apiKey: ""
  reasoningEffort: null
  maxTokens: 12000
  timeoutSeconds: 300
```

Replace `local-model` with the model ID served by both interfaces below. This
option uses the existing Codex coding harness against your endpoint. It does not
install or serve model weights. Omit `reasoningEffort` or set it to `null` when
the service does not support the optional reasoning parameter. If authentication
is required, `apiKey` becomes a Bearer token; otherwise leave it empty.

| Workflow | Required endpoint capabilities |
| --- | --- |
| Inspector QA, rules-only translation and harness translation | `POST /chat/completions`, non-streaming JSON responses, system/user messages and `max_completion_tokens`. Text must be in `choices[0].message.content` with `finish_reason: stop`, and satisfy the workflow's JSON contract. |
| Application porting | Chat Completions with `response_format: {type: json_schema, ...}` for planning, plus `POST /responses` with Codex-compatible streaming and tool calls for coding stages. |
| Repository back-translation and alignment | `POST /responses` with Codex-compatible streaming and tool calls. |

`baseUrl` is the API prefix, including `/v1` when the service uses it; do not
include `/chat/completions` or `/responses`. The adapters append these routes.
The relay forwards Responses requests without converting them into Chat
Completions. A service exposing only Chat Completions cannot run the full port
or repository-reading workflow. Coding stages still require the installed
Codex CLI and Docker. A compatible local Messages service can instead use the
`anthropic` section, with `/messages` for data-only calls and Claude Code's
streaming, tool-use and `/messages/count_tokens` interfaces for coding sessions.
Responses support means accepting the installed Codex CLI's actual tool
definitions, tool-call results and multi-turn requests, and producing its
expected SSE event stream. Merely exposing a route named `/responses` is not
sufficient. The adapter pins the configured model and does not switch providers
or translate Responses into Chat Completions when a request fails.

`./install.sh --provider codex-compatible-local-endpoint` prepares Codex and the
same execution images. The default installer already prepares both coding CLIs.

The URL must use HTTPS, or HTTP on loopback (`localhost`, `127.0.0.1` or `::1`).
Plain HTTP on a LAN address or a Docker hostname is rejected. The endpoint must
be reachable from the PolicyWeave host; coding containers reach it through the
host relay. Redirects are rejected. Data-only responses are limited to 8 MiB;
`maxTokens` accepts a positive integer and `timeoutSeconds` accepts 1–3,600 for data-only calls.
Port planning defaults to 128,000 tokens unless configured otherwise. Choose
budgets that fit the model's context window; source bundles and generated rules
must fit, and host validators still reject invalid or incomplete output.
The planning budget leaves room for reasoning as well as the complete JSON plan;
it is an upper limit, not a target output length. The [reported port](https://github.com/thaddywu/CS239-Phase2/issues/8) needed about
30,000 output tokens and succeeded with a 64,000-token cap; 128,000 doubles that
successful cap to leave room for harder plans and additional reasoning. Planning
artifacts use the shared 4 MB read limit, including accepted and repaired drafts.
The planning source bundle accepts up to 2,000,000 characters of selected source
evidence, retaining complete files rather than truncating them. Combined source,
contracts, repair drafts and the output budget still need to fit the endpoint's
context window. The longer default planning timeout leaves room for large inputs
and reasoning; explicit connection settings remain authoritative.
The endpoint enforces its own supported token limits. Truncated responses report
the configured `maxTokens`; raise it in the selected connection section when needed.
Failed planning calls retain a private `STAGE-attempt-N-error.json` with the stage,
failure kind, token budget, elapsed time, and available HTTP status, finish reason
and numeric usage. Provider error bodies and partial output are excluded.

### Shared connection behavior

Use the same `--connection /path/to/private-connection.yaml` for `port`,
`back-translate`, review, rules-only translation, analyze and inspect. Keep the
file outside both application checkouts and outputs; `chmod 600` restricts local
access. The student runner owns its application's model setup separately;
PolicyWeave does not inject the translator's credentials into the application.
Provider-neutral transports can still implement `generate(stage, prompt)`.
No particular hosted provider is required by the core.

### Connection entry points and extension boundaries

Every YAML entry goes through `adapters/model_settings.load_connection`. The
student loader delegates to it when a file is supplied. `Connection` means the
shared data-only transport in `adapters/compatible.py`; `CodexPort` composes the
existing isolated coding session, including Claude Code when Messages is selected.

| Entry | Model adaptation |
| --- | --- |
| `policyweave port` | Student loader; `CodexPort.plan()` uses `Connection` for inventory/binding, then `CodingAgent` for rules/instrumentation, independent reading and alignment. |
| `policyweave add` / `policy-add` | Same student port workflow. With no YAML, this older entry retains the `POLICY_*` environment fallback. |
| `policyweave back-translate` | Student loader; `CodexPort` coding sessions for independent repository reading and alignment. |
| `policyweave translate` / `policy-translate` | `Connection` only; requires an existing binding. |
| `policyweave backtranslate` / `policy-backtranslate` | `Connection` only; reads supplied JSON implementation evidence rather than a repository. |
| `policyweave translate-harness` | `Connection` only; `CONNECTION_FILE` may supply the YAML path. This adapts the student's test harness, independently of the coding-agent harness. |
| `policyweave inspect` | Optional `Connection` for read-only QA; viewing itself needs no model. |
| `policyweave analyze` / `policy-analyze` | `Connection` for `--question`; deterministic queries/replay need no model. |
| `policyweave review`, `view-translation` / `policy-review` | Optional `Connection` for workbench model actions; repository translation controls also compose `CodexPort`. Viewing and human judgments need no model. |
| `policyweave pipeline` | Student port workflow followed by `Connection` for trajectory QA. |
| `policyweave enforce` / `policy-enforce`; `run-cases` / `policy-run-cases` | No framework model connection; the application owns any model calls it makes. |
| `python -m policyweave.policy_adder.codex` | Low-level stage CLI; shared YAML loader and the same `CodexPort` planning/coding paths. |

The two transports are selected from the loaded `protocol`: `chat-completions`
uses Chat Completions directly and Codex/Responses for coding; `messages` uses
native Messages and Claude Code. Coding requests pass through
`adapters/model_proxy.py`, which holds credentials on the host, limits routes and
models, and forwards streaming. The application runtime and generated student
runner do not receive this model connection automatically.

To add another endpoint using either supported protocol, configure `baseUrl`,
`modelId` and the existing optional fields; no new adapter is necessary. A named
profile belongs in `model_settings.PROVIDERS`, with explicit defaults and
selection rules, plus the public template, setup guide and course instructions.
Add deterministic loader, transport and coding/relay conformance cases under
`tests/adapters`; credentials must stay out of commands, mounts and artifacts.

A genuinely new HTTP protocol requires wire translation in `adapters`, shared
settings/header validation and a restricted relay route. A new coding harness
must implement the existing `CodingAgent` session boundary: executable lookup,
mounts, environment, arguments and successful completion handling, while reusing
the Docker, frozen-input and artifact-validation boundaries. Add its optional
installer mapping in `install_tools.py` and `install.sh`. Keep protocol or
provider branches out of the five domain modules. The new local profile adds no
protocol or harness, so it needs no separate network implementation.

Install the optional
[Claude Code native CLI](https://code.claude.com/docs/en/setup) for app-port and
repository-reading sessions; data-only translation and inspect need no coding
CLI. The adapter was exercised with Claude Code 2.1.252. It requires `--bare`,
`--setting-sources`, `--strict-mcp-config`, `--no-session-persistence` and
`--tools`; a CLI that rejects these flags fails the session. `codingCommand` may
name a different installed executable, without shell arguments. It applies to
either coding adapter; the existing `--codex` override remains available for Codex.

Set `reasoningEffort: null` to use the model default. Messages accepts
`low`, `medium`, `high`, `xhigh` and `max`, subject to model support. Generic
`headers` can supply an API version or workspace header when required by the
endpoint; credentials still belong in `apiKey`, and transport/auth overrides and
header line breaks are rejected. YAML aliases, duplicate keys, unsafe tags and
oversized documents fail without echoing source lines or keys. No provider-specific
environment setup is needed.

Native Messages uses [structured JSON output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
for schema-bearing stages. Unsupported wire bounds are moved to schema
descriptions; the original host inventory/binding/reading validators still enforce
their limits. Truncated, refused or tool-bearing data-only responses fail rather
than becoming successful drafts. Numeric usage is normalized to the same fields
as the Chat Completions adapter.

Claude Code runs non-interactively inside the existing credential-free,
network-isolated Docker boundary, with only Read, Edit and Bash tools, ephemeral
configuration, no inherited project/user settings, skills or MCP servers. A
temporary relay credential reaches only the host-selected model's Messages and
token-count routes. The real key stays on the host. The relay preserves message
and tool payloads, forwards streaming and version/beta headers, rejects model
switching and redirects, and redacts upstream error bodies. A successful process
exit also needs a successful terminal CLI result; existing stage validators then
check produced artifacts. Both coding adapters use identical source protection,
binding/rule freezes, native checks, independent reverse inputs and alignment.

Shared offline conformance tests run with `python -B -m tests`. To additionally
exercise the actual native CLI and Docker with a local synthetic Messages server:

```bash
python -B tests/adapters/claude_smoke.py --image policy-portin:batch-v1
```

That check verifies a real tool loop, a rejected write to a frozen input and a
generated output without a provider key or live model. It is transport/isolation
evidence, not a model-driven application-port evaluation.

Credentials remain in the host relay, outside application containers. Original/framework mounts are read-only; application checks run in credential-free containers without general network access. Logs, source snapshots, failed attempts, model usage and generated trajectories stay in private output directories. The shared [port contract](../src/policyweave/policy_adder/porting-contract.md) states the exact adaptation obligations and limits.

```bash
policyweave view-translation --back-translation /path/to/enforced-app/back-translation \
  --policy /path/to/original-app/policy.md
```

The view opens at `http://127.0.0.1:5190`; use `--port` to select another port.
`policyweave review` remains an alias for the same view.

Each application needs its own reset/replay and authoritative observation integration. The generic port adapter does not automatically supply a research runner for every repository. The [demo](../demo/README.md) exercises the shared harness with synthetic LabCluster data.

## Student runner

Students write a single Python `run.py` that starts their original app, initializes
and drives each scenario, and checks actual effects and final responses against
`test_cases.json`. Use an `APP_DIR` variable to locate the app. No fixed callback
names or file split is required. The original harness implements `--case`,
`--side original`, `--output_dir` and `--sample` (repetitions per case).
Save `OUTPUT/CASE/SIDE/sample-N/result.json` containing exactly
`{"task_complete": true}` or `{"task_complete": false}`. Keep intermediate app
outputs in the episode's `artifacts/` directory. False also covers a timeout or
execution error that prevents confirming completion. A gate verdict or an agent's
claim does not establish task completion.

### Translate the harness

With the same exported application paths and model connection as porting:

```bash
policyweave translate-harness \
  --input run.py --output translated_harness.py \
  --original-app "$ORIGINAL_APP_DIR" --ported-app "$PORTED_APP_DIR" \
  --connection "$CONNECTION_FILE"
python translated_harness.py --case S02 --side original --output_dir runs --sample 1
python translated_harness.py --case S02 --side ported --output_dir runs --sample 1
```

`--input` and `--output` are required Python filenames. The original harness stays
unchanged and output must be new. `ORIGINAL_APP_DIR`, `PORTED_APP_DIR` and
`CONNECTION_FILE` supply translation defaults; optional `--original-app`,
`--ported-app` and `--connection` flags override them. The translated harness uses
the same command-line interface (CLI) as the original harness, adding support for
`--side ported`. Application-directory flags belong to `translate-harness`.

The data-only model receives the harness, adjacent `test_cases.json` if present,
bounded Python source from both apps (prioritizing harness imports and startup
entrypoints), and the shared runner contract. It receives no connection settings,
keys, `.env` files, run artifacts or original policy text. Translation generates
application launch integration; it does not execute the apps. The host preserves
original helper/checker definitions except declared startup functions, retains
assertions, checks syntax and appends a deterministic shared CLI. The adjacent
`.translation.json` report records hashes and integration limitations. These
checks do not prove semantic equivalence for arbitrary inline test logic; review
the generated startup changes and run the harness. The apps are unchanged.

The generated callback runs one episode and returns the student's completion
verdict. The framework sets `APP_DIR` for the selected side before application
import/initialization. It owns repetitions, trajectory export and single-field
results; diagnostics remain separate in `run.json`. Existing episode directories
are never overwritten. `--output-dir` remains an alias for `--output_dir`.

After every invocation, the generated entry point scans all current
`OUTPUT/CASE/SIDE/sample-N/result.json` files and prints:

```text
Until now, original app: 85/100 runs completed the task.
Until now, ported app: 80/100 runs completed the task.
```

Each file counts one sample. Earlier results outside the latest case/sample
selection count too; a side with no files reports `0/0`. Malformed results fail
the summary instead of silently changing counts. The original student harness
does not implement this reporting. No separate statistics command is needed.

### Recording responsibilities

Port-in installs hooks at real model, tool, message and state boundaries. The
framework recorder and translated launcher own capture lifecycle and export:
`trajectory.json`, equivalent `trajectory.jsonl` and native `gate-N.json` evidence.
Students neither serialize events nor read the schema. Original runs need no
trajectory; failed ported runs retain available evidence and an already obtained
task verdict. Missing gate capture is a recording failure, independently of task
completeness.

The generated launcher cannot observe a subprocess or remote server through a
parent recording context alone. Those apps need an existing child-side capture
and export integration installed during port-in. Unresolved paths belong in the
translation limitations; generating an empty timeline does not establish capture.
The [timeline schema](timeline.md#conversation-and-tool-log-contract) and
[gate contract](trajectory.md#version-1-contract) remain framework interfaces.

```bash
policyweave inspect --traj runs/S02/ported/sample-1/trajectory.json --connection connection.yaml
```

The course materials include a trajectory example/schema in an optional appendix.
A small [LabCluster original harness](../examples/harnesses/labcluster.py) exercises
one real application scenario with its explicitly deterministic offline backend;
it includes no PolicyWeave imports, recording or statistics.
