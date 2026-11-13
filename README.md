# PolicyScope

Add natural-language policies to applications, independently read the implementation back, review correspondence, enforce actions and analyze captured policy state.

| Module | Source | Responsibility |
| --- | --- | --- |
| Policy adder | [policy_adder](src/policyscope/policy_adder/README.md) | Requirements, rules and isolated application adaptation |
| Back-translation | [back_translation](src/policyscope/back_translation/README.md) | Independent descriptions from implementation evidence |
| Policy viewer | [policy_viewer](src/policyscope/policy_viewer/README.md) | Source alignment and human review |
| Enforcement | [enforcement](src/policyscope/enforcement/README.md) | Trusted action gate and staged fact updates |
| Analysis | [analysis](src/policyscope/analysis/README.md) | Trajectory QA, decision replay, snapshot queries and hypotheticals |

The Python core requires no hosted model, Grokbot, Node or Docker. Native execution needs Soufflé 2.5 and Linux `prlimit`. Model and sandbox connections are optional adapters.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
policyscope review                 # http://127.0.0.1:5190
policyscope inspect trajectory.json # read-only timeline, http://127.0.0.1:5191
```

The review opens a synthetic document example without a model or native engine. For execution, install [the native engine](docs/setup.md), then run:

```bash
python examples/quickstart/quickstart.py
policyscope run-cases --cases examples/cases/document-tests.json --data ../policyscope-runs/example
python -B -m tests
```

Application adaptation uses an optional coding-agent/Docker adapter. See [setup](docs/setup.md), [porting](docs/porting.md) and the [student workflow](docs/study/student-workflow.md). `policyscope pipeline` connects all five modules, including actual gate capture and read-only QA; see the [trajectory contract](docs/trajectory.md). The shared UI currently provides translation controls and sentence review; it does not yet expose five separate tabs.

The [trajectory viewer](docs/timeline.md) independently reads conversation/tool logs
with declared participants, plus existing gate trajectories. It has no model or
application connection and preserves directed recipients in one observer timeline.

[Repository map](docs/repository-structure.md) · [Documentation](docs/README.md) · [Archives and migration limits](docs/archives.md) · [Contributing](.github/CONTRIBUTING.md) · [License](LICENSE)
