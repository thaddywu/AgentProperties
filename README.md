# AgentProperties — archived pre-rewrite work

This branch is a frozen snapshot. Active development restarted from an empty
root on `master`; nothing here is maintained.

## Why it was archived

Every application study on this branch shared one defect: **the policy handed to
the model was itself unsound** — ambiguous, under-specified, or internally
inconsistent. The agent was then scored against those rules, so the numbers
measure prompt defects rather than agent behavior. That is not fixable by
re-running; the policy specification has to be built correctly first, which is
what `master` starts over on.

Read the results here as a record of what was tried, not as findings.

## Layout

| Path | What it is |
| --- | --- |
| `applications/` | Six application studies: `opsdesk` (the most developed), plus `cloud`, `consent`, `filesystem`, `incident`, `payout`. Each has its own `DESIGN.md`/`README.md`, prompts, protocols, and recorded traces. |
| `applications/*/results/` | Sweep outputs and per-run JSONL traces. Directories were deliberately made read-only to keep runs from being overwritten. |
| `shared/` | The common harness: `agentloop.py`, `promptgrid.py`, `sweep.py`, `trace.py`, `diagnose.py`, `recompute.py`. |
| `survey/` | Literature and benchmark survey. `dataset.md` and `pointer.md` carry the per-benchmark notes and file-level pointers into `datasets/`. |
| `examples/` | Curated per-benchmark trace excerpts referenced by `survey/pointer.md` (`open-swe-traces/`, `trail/`). |
| `REPORT.md`, `3apps.md`, `1.md` | Working write-ups. |

`examples/toolbench/` (~64M, 7.8k files) is *not* tracked — it is a bulk
extraction regenerable from `datasets/ToolBench`.

## Datasets (~40G, none of it stored in this repo)

`datasets/` is third-party benchmark corpora. It is never vendored here.
Provenance and exact revisions live in [`datasets.lock.json`](datasets.lock.json).

Seven upstream checkouts are **git submodules**, pinned to the commits actually used:

```sh
git submodule update --init          # ~2G
```

The other four have no upstream `.git` (they were `snapshot_download`ed or
copied), so they are pinned by repo id + revision and refetched by script:

```sh
./scripts/fetch_datasets.sh              # everything, ~40G
./scripts/fetch_datasets.sh submodules   # just the submodules, ~2G
./scripts/fetch_datasets.sh TRAIL        # one by name
```

| Dataset | Size | Source | Pinned |
| --- | --- | --- | --- |
| `Open-SWE-Traces` | 18G | HF `nvidia/Open-SWE-Traces` | `9c0e4579` — verified: revision resolves and its manifest matches the local tree |
| `ToolBench` | 21G | HF `nullwwg/toolbench-data` | `f31e7988` — verified: repo root is exactly `data.zip` + `reproduction_data.zip`, matching the cached LFS metadata |
| `TRAIL` | 179M | HF `PatronusAI/TRAIL` | **unpinned** — no revision was recorded at download time, so a refetch gives current `main`, not necessarily these bytes |
| `ha-ultimate` | 104K | `github.com/openclaw/skills` | `134f128e` (v1.0.2), from the snapshot's own `_meta.json` |

`ToolBench` ships as zips upstream; the layout used here is the expanded form,
and the fetch script expands it for you.

### Where the local copy went

The ~40G working copy was moved out of the repo on 2026-08-31 to keep the
checkout small; it now lives at `~/Agent-datasets/datasets`, with the
`examples/toolbench` bulk extraction beside it at `~/Agent-datasets/examples`.
The seven submodule checkouts moved with it and are intact at the pinned
commits, so you can point tooling at that path instead of refetching. A fresh
clone that just wants the data should use the commands above.
