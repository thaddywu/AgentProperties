# self-create-application

A benchmark scenario built from scratch, after surveying existing agent benchmarks and finding
none that could express the property we wanted.

**Start with [`OVERVIEW.md`](OVERVIEW.md)** — the whole benchmark in under ten minutes.

| Directory | Contents |
|---|---|
| [`design/`](design/) | [`v0.md`](design/v0.md) — the scenario and why the property needs both lifecycle and information flow. [`tasks.md`](design/tasks.md) — T1–T8. [`archive/`](design/archive/) — the superseded, larger "OpsDesk" design, kept for reference. |
| [`code/`](code/) | The frozen implementation: world, checker, agents, sweeps. See [`code/README.md`](code/README.md) to run it. |
| [`results/`](results/) | Frozen traces and findings: `sweep-01/` (T1/T2/T7), `sweep-02/` (robustness variants), `checker-validation/`, `discarded/`, `logs/`. |
