# PolicyWeave

Add natural-language policies to applications, independently read the implementation back, review correspondence, enforce actions and analyze captured policy state.

| Module | Source | Responsibility |
| --- | --- | --- |
| Policy adder | [policy_adder](src/policyweave/policy_adder/README.md) | Requirements, rules and isolated application adaptation |
| Back-translation | [back_translation](src/policyweave/back_translation/README.md) | Independent descriptions from implementation evidence |
| Policy viewer | [policy_viewer](src/policyweave/policy_viewer/README.md) | Source alignment and human review |
| Enforcement | [enforcement](src/policyweave/enforcement/README.md) | Trusted action gate and staged fact updates |
| Analysis | [analysis](src/policyweave/analysis/README.md) | Trajectory QA, decision replay, snapshot queries and hypotheticals |

The Python core requires no hosted model, Grokbot, Node or Docker. Native execution needs Soufflé 2.5 and Linux `prlimit`. Model and sandbox connections are optional adapters.

For translation setup, run `./install.sh`, then `source .venv/bin/activate`.
It prepares native tools and Docker images without reading or changing API keys.
See [manual installation](docs/setup.md) if a prerequisite is missing.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
policyweave review                 # http://127.0.0.1:5190
policyweave inspect --traj trajectory.jsonl --connection connection.yaml # http://127.0.0.1:5191
```

The review opens a synthetic document example without a model or native engine. For execution, install [the native engine](docs/setup.md), then run:

```bash
python examples/quickstart/quickstart.py
policyweave run-cases --cases examples/cases/document-tests.json --data ../policyweave-runs/example
python -B -m tests
```

`policyweave translate-harness --input run.py --output translated_harness.py --original-app ORIGINAL --ported-app PORTED --connection CONNECTION.yaml`
adapts a single original-app harness for original/ported execution, trajectory
export and cumulative task-completion counts, using the shared application paths
and connection settings. See [the harness workflow](docs/porting.md#student-runner).

Application adaptation uses an optional coding-agent/Docker adapter. `policyweave port --input ORIGINAL --output PORTED --connection CONNECTION.yaml` includes independent back-translation and alignment; `--no-back-trans` separates them. `policyweave back-translate` reads an installed app into a new review bundle. Copy [connection.yaml](examples/connection.yaml) outside the repository and fill the `openai` or `anthropic` key. `provider: auto` selects the filled section, preferring OpenAI when both keys are filled; set `provider: anthropic` to select Claude explicitly. For a self-hosted model, select `provider: codex-compatible-local-endpoint` and fill its `baseUrl` and `modelId`; see [required APIs](docs/porting.md#local-model-endpoints). Start Inspector with the same `--connection` YAML file for trajectory review and QA. See [setup](docs/setup.md), [porting and the student runner contract](docs/porting.md) and the [Phase 2 course materials](docs/phase2-hw-release/phase2-instructions.tex). `policyweave pipeline` connects all five modules, including actual gate capture and read-only QA; see the [trajectory contract](docs/trajectory.md). The shared UI currently provides translation controls and sentence review; it does not yet expose five separate tabs.

The [trajectory viewer](docs/timeline.md) independently reads conversation/tool logs
with declared participants, plus existing gate trajectories. It preserves directed
recipients in one observer timeline. The standard Inspector workflow supplies
`--connection` for QA, which translates questions into bounded read-only Datalog. It cannot interact with the
recorded agents. Application execution uses a separately registered trusted runner.

[Repository map](docs/repository-structure.md) · [Documentation](docs/README.md) · [Contributing](.github/CONTRIBUTING.md) · [License](LICENSE)
