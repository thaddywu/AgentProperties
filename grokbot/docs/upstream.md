# Updating the Rakazo host

Grokbot is a modified [Rakazo](https://github.com/elie222/rakazo) host. Its original `apps/`, `packages/`, `infra/`, `scripts/`, `patches/` and operational `docs/` now live together under `grokbot/`. Git history is preserved. `grokbot/upstream-base` records the last upstream revision incorporated before the policy-demo changes.

The root workspace configuration belongs to this repository. The Nova application, policy runtime and translator are separate packages. This keeps most upstream host changes in the same relative layout, although imports, workspace links and policy/UI integration may still conflict. This is a fork with a reviewable update path; updates are not automatic.

## Prepare an update

From the repository root, add the upstream remote once, then fetch when an update is wanted:

```bash
git remote add rakazo-upstream https://github.com/elie222/rakazo.git
git fetch rakazo-upstream
bash grokbot/scripts/upstream-diff.sh rakazo-upstream/main
```

If the remote already exists, skip `remote add`. The helper itself performs no network requests. It writes ignored artifacts under `grokbot/.upstream/<target-commit>/` and changes neither source nor the recorded baseline:

- `host.patch`: changes to the original host directories, ready for the `grokbot/` path prefix.
- `workspace-review.patch`: changes to root files, CI and other directories, for manual integration into this workspace.
- `summary.txt` and `revisions.txt`: scope and exact source revisions.

Review an update in a disposable worktree. After committing any current work, create one with `git worktree add --detach <review-directory> HEAD`. From that checkout, a reviewed host patch can be applied with:

```bash
git apply --3way --directory=grokbot /path/to/host.patch
```

Three-way application can leave conflicts; resolve them while retaining the policy integration. Review root changes individually instead of applying `workspace-review.patch` wholesale: upstream README/workspace files must not overwrite this repository's layout, and generated lockfiles should be regenerated without unintended dependency upgrades. Review any upstream deletions or moves of files that have since been extracted into `apps/nova/` or `runtime/`.

Run the affected host tests, workspace type checks, Nova gate/query tests and translation tests. UI changes also need the relevant web E2E coverage; leave Electron E2E to CI. Advance `grokbot/upstream-base` to the target hash only when the complete intervening update has been integrated and verified. Cherry-picking a few fixes does not advance the baseline.
