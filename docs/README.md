# Documentation

Start with the [repository README](../README.md) for installation and module entry points.

| Guide | Contents |
| --- | --- |
| [Setup](setup.md) | Installation, native engine and offline checks |
| [Repository structure](repository-structure.md) | Five modules and dependency boundaries |
| [Porting](porting.md) | Optional isolated application adaptation and model connection |
| [Trajectory contract](trajectory.md) | App boundaries, captured evidence, read-only QA and five-module pipeline |
| [Trajectory viewer](timeline.md) | Read-only conversation/tool timeline, participant schema and import limits |
| [Three-app experiment](evaluation/three-app-pipeline.md) | Complete module runs, measured results and remaining policy gaps |
| [LabCluster Tasks 3–5 pilot](study/labcluster-pilot.md) | Five paired cases, raw logs, completion/violation checks and UI analysis |
| [LabCluster pilot results](evaluation/labcluster-pilot.md) | Paired execution measurements, query evaluation and retained counterexample |
| [Student workflow](study/student-workflow.md) · [中文](study/student-workflow.zh.md) | Translate, review and record application tests |
| [Evaluation protocol](study/protocol.md) | Research judgments, evidence and study limits |
| [Archives](archives.md) | Previous implementations, experiment evidence and branch recovery |

The student guide is the source document. Generate its PDF only when needed; its default destination is `~/.cache/policyscope/docs/student-workflow.pdf` (respecting `XDG_CACHE_HOME`):

```bash
python -m pip install '.[test]' markdown-it-py
python -B docs/study/build_pdf.py
```

The canonical manuscript remains in the optional `docs/research` Git submodule. Core commands do not initialize or require it. Initialize it only when working on the paper; build `docs/paper.tex` from the repository root. Commit paper changes in the submodule before updating its revision here.
