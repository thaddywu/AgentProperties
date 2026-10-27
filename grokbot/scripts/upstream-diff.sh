#!/usr/bin/env bash
# Export reviewable upstream changes. Never fetch, apply patches or change the baseline here.
set -euo pipefail
workspace="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$workspace"
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo 'Usage: bash grokbot/scripts/upstream-diff.sh <upstream-ref> [new-output-directory]' >&2
  exit 2
fi
read -r baseline < grokbot/upstream-base
baseline="$(git rev-parse --verify --end-of-options "${baseline}^{commit}")"
target="$(git rev-parse --verify --end-of-options "${1}^{commit}")"
if ! git merge-base --is-ancestor "$baseline" "$target"; then
  echo 'The target does not descend from the recorded Rakazo baseline.' >&2
  exit 1
fi
output="${2:-grokbot/.upstream/$target}"
if [[ -e "$output" || -L "$output" ]]; then
  echo 'Output already exists; choose a new directory.' >&2
  exit 1
fi
mkdir -p "$(dirname "$output")"
mkdir "$output"
git diff --binary --full-index "$baseline" "$target" -- \
  apps packages infra scripts patches docs > "$output/host.patch"
git diff --binary --full-index "$baseline" "$target" -- . \
  ':!apps' ':!packages' ':!infra' ':!scripts' ':!patches' ':!docs' > "$output/workspace-review.patch"
git diff --stat "$baseline" "$target" > "$output/summary.txt"
printf 'baseline=%s\ntarget=%s\n' "$baseline" "$target" > "$output/revisions.txt"
echo 'Exported host.patch, workspace-review.patch, summary.txt and revisions.txt.'
echo 'Review before applying. The workspace and recorded baseline have not changed.'
