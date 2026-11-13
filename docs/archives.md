# Archives and migration

Before restructuring, the pending implementation was committed and preserved with its dependencies. The tag `archive/pre-restructure-2026-11-12` identifies the complete snapshot. Five remote branches identify the five modules:

| Branch | Preserved implementation |
| --- | --- |
| `archive/policy-adder` | Forward translator and application porting controllers |
| `archive/back-translation` | Rule and implementation reading |
| `archive/policy-viewer` | Python and historical web review UIs |
| `archive/enforcement` | Python and TS runtimes, application ports |
| `archive/post-mortem` | Python query layer, Nova analysis, proof trees and action search |

Each branch contains the complete runnable context and its own `ARCHIVE.md`. These are frozen backups, not five active development lines. Earlier branch tips are preserved as tags listed in [branches.json](archive/branches.json); deleting the old branch names does not delete those commits.

The archives include the original public experiment artifacts under `docs/evaluation`. [experiment-summary.json](archive/experiment-summary.json) preserves selected aggregate metrics from ignored local reports. Raw private prompts, source copies, trajectories, endpoints and logs were excluded from publication. Local private originals and a Git bundle remain in ignored backup storage.

```bash
git fetch origin --tags
git show archive/post-mortem:ARCHIVE.md
git worktree add --detach /path/to/archive origin/archive/post-mortem
```

Active Python imports now use `policyscope.*`; the previous `policy_runtime`, `policy_translation`, `policy_query` and `policy_evaluation` source roots are archived. Install the root distribution with `pip install -e .`. The UI entry is `policyscope review`, verification is `python scripts/check.py`, and adapter containers use `src/policyscope/adapters/Dockerfile`.

This restructure preserves the Python snapshot/query behavior and the review UI. It does not claim Python parity with Nova's TS proof trees, distributed reconstruction, minimum-event prevention or completion-path search. Those implementations remain available in the post-mortem archive. A unified historical trajectory contract, deletion/revocation replay and five UI tabs are deferred.
