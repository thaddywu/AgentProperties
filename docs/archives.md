# Archives and migration

Before restructuring, the pending implementation was committed and preserved with its dependencies. The tag `archive/pre-restructure-2026-11-12` identifies the complete snapshot. Five remote branches identify the five modules:

| Branch | Preserved implementation |
| --- | --- |
| `archive/policy-adder` | Forward translator and application porting controllers |
| `archive/back-translation` | Rule and implementation reading |
| `archive/policy-viewer` | Python and historical web review UIs |
| `archive/enforcement` | Python and TS runtimes, application ports |
| `archive/post-mortem` | Python query layer, Nova analysis, proof trees and action search |

Each branch contains the complete runnable context and its own `ARCHIVE.md`. These are frozen backups, not five active development lines. Earlier branch tips are preserved under `archive/branches-2026-11-12/*` tags. The first consolidated Python layout is retained as `archive/python-layout-2026-11-12`.

Historical evidence belongs to these archives. They contain the original public results under `docs/evaluation`, aggregate measurements and the earlier branch inventory under `docs/archive`. Raw private prompts, source copies, trajectories, endpoints and logs were excluded from publication. Local private originals and Git bundles are retained outside the checkout.

```bash
git fetch origin --tags
git show archive/post-mortem:ARCHIVE.md
git show origin/archive/policy-adder:docs/archive/experiment-summary.json
git tag --list 'archive/branches-2026-11-12/*'
git worktree add --detach /path/to/archive origin/archive/post-mortem
```

Active Python imports use `policyscope.*`. The previous `policy_runtime`, `policy_translation`, `policy_query` and `policy_evaluation` source roots are archived. Current commands and verification are documented in [setup](setup.md) and the repository README; one-off restructure reports remain in the layout snapshot.

The Python implementation now supports captured gate trajectories, decision replay
and bounded QA through a [shared contract](trajectory.md), including snapshots
after recorded fact deletion/replacement. It does not claim parity with Nova's TS
proof trees, distributed reconstruction, minimum-event prevention or completion-path
search. Those implementations remain in the post-mortem archive. Five UI tabs are
still deferred.
