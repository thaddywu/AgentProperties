# AgentProperties

Clean restart. The previous line of work is archived, not deleted.

## Why the restart

Every earlier application study (opsdesk, cloud, consent, filesystem, incident,
payout) shared one defect: **the policy handed to the model was itself unsound.**
The agent was scored against rules that were ambiguous, under-specified, or
mutually inconsistent, so the measurements captured prompt defects rather than
agent behavior. No amount of re-running fixes that; the policy specification has
to be built correctly first.

## Where the old work lives

| Branch | Contents |
| --- | --- |
| `archive-tsm-fs-spec` | Full snapshot: all five applications, `shared/` harness, `survey/`, `examples/`, all sweep results and traces. Tip commit `5a87426`. |
| `archive-master` | The pre-experiment `master` line. |

Recover any path without switching branches:

```sh
git checkout archive-tsm-fs-spec -- applications/opsdesk
```

## Datasets

`datasets/` (~40G) is third-party benchmark corpora — cloned or downloaded, never
vendored into this repo, and gitignored on every branch. Provenance and per-file
pointers are on `archive-tsm-fs-spec` in `survey/dataset.md` and
`survey/pointer.md`. Nothing here reconstructs it automatically; re-fetch from
the upstream sources listed there.
