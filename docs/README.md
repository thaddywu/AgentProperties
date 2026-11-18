# Documentation

Start with the [repository README](../README.md) for a runnable example and module entry points.

## Current guides

| Guide | Contents |
| --- | --- |
| [Setup](setup.md) | Installation, native engine and offline checks |
| [Repository structure](repository-structure.md) | Five modules and dependency boundaries |
| [Porting](porting.md) | Optional isolated application adaptation and model connection |
| [Trajectory contract](trajectory.md) | App boundaries, captured evidence, read-only QA and five-module pipeline |
| [Trajectory viewer](timeline.md) | Read-only conversation/tool timeline, participant schema and import limits |

## Course materials

The merged [Phase 2 instructions](phase2-hw-release/phase2-instructions.tex) live in the Overleaf Git submodule at `docs/phase2-hw-release`. Configure its private clone URL locally before initializing it; replace `PROJECT_ID` below with the project's ID:

```bash
git config submodule.phase2-course-materials.url https://git@git.overleaf.com/PROJECT_ID
git submodule update --init -- docs/phase2-hw-release
```

Inside that submodule, use `git pull --ff-only` to get editorial updates. Commit and push source edits within the submodule, then commit its updated revision in the parent repository. The previous two-document release is preserved on branch `archive/phase2-hw-release-2026-11-16` at commit `4dcc69d7`.

### Publish CS239-Phase2

Keep developing in this repository. With the working tree and course submodule committed, run:

```bash
python -B docs/course/publish.py --push
```

This runs the offline tests, exports the committed framework, demo and guides, builds the course PDF with `latexmk`, and pushes a normal commit to CS239-Phase2's `main` branch. It uses the existing Git SSH authentication and leaves this repository's remote unchanged. `release.json` records both source revisions. Local configuration, runs, manuscript files and historical reports are excluded. Edit the course repository's landing page in [course/README.md](course/README.md).

To inspect an export before publishing, use a new directory:

```bash
python -B docs/course/publish.py --output /path/to/course-release
```

The export reads committed files only; it rebuilds the PDF from those exact sources and requires every referenced screenshot. It never copies a local PDF. Verify the release tool offline with `python -B -m unittest discover -s docs/course -p 'test_*.py'`.

## Design

- [Observations and translation](design/observations-and-translation.md): fact producers, shared schemas, agent authority and rule/binding boundaries.
- [Staged port workflow](design/port-pipeline.md): four enforced host stages, binding/rule freezes, native trace checks and later independent review; remaining semantic and coverage limits.
- [Back-translation workflow](design/back-translation-workflow.md): frozen implementation inputs, independent enforcement reconstruction, concise student descriptions and separate source alignment.

The manuscript lives in the optional `research/` Git submodule. Initialize it only for paper work, build `docs/paper.tex` from the repository root, and commit manuscript changes in the submodule before updating its revision here. See [repository history](repository-structure.md#historical-implementations) for frozen implementations and recovery commands.
