# self-create-application

A benchmark scenario built from scratch, after surveying existing agent benchmarks and finding none
that could express the property we wanted.

**Start with [`OVERVIEW.md`](OVERVIEW.md)** — the whole thing in two pages.

| Directory | Contents |
|---|---|
| [`code/`](code/) | The frozen implementation: world, checker, agents, sweeps. [`code/README.md`](code/README.md) says how to run it. |
| [`results/`](results/) | Frozen traces and findings: `sweep-01/` (T1/T2/T7), `sweep-02/` (robustness variants), `checker-validation/`, `discarded/`, `logs/`. |
| [`design/archive/`](design/archive/) | Superseded and long-form documents, kept for background: the scenario argument (`v0.md`), task definitions T1–T8 (`tasks.md`), the full formalization (`property.md`), three worked trace timelines (`trace-walkthrough.md`), and the earlier larger "OpsDesk" design. |
