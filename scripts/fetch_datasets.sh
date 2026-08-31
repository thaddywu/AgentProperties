#!/usr/bin/env bash
# Restore datasets/ from datasets.lock.json. Nothing under datasets/ lives in
# this repo: the seven upstream checkouts are submodules, the other four are
# refetched from Hugging Face / GitHub at the pinned revision.
#
#   ./scripts/fetch_datasets.sh            # everything (~40G)
#   ./scripts/fetch_datasets.sh submodules # just the 7 git submodules (~2G)
#   ./scripts/fetch_datasets.sh TRAIL      # one dataset by name
set -euo pipefail
cd "$(dirname "$0")/.."
what="${1:-all}"

need() { command -v "$1" >/dev/null || { echo "missing required tool: $1" >&2; exit 1; }; }

if [[ "$what" == "all" || "$what" == "submodules" ]]; then
  echo "==> submodules (~2G)"
  git submodule update --init --recursive
  [[ "$what" == "submodules" ]] && exit 0
fi

need python3
hf() { # repo_id revision dest
  local repo="$1" rev="$2" dest="$3"
  if [[ "$rev" == "null" || -z "$rev" ]]; then
    echo "    !! UNPINNED - fetching current main" >&2
    rev="main"
  fi
  python3 - "$repo" "$rev" "$dest" <<'PY'
import sys
from huggingface_hub import snapshot_download
repo, rev, dest = sys.argv[1:4]
snapshot_download(repo_id=repo, revision=rev, repo_type="dataset",
                  local_dir=dest, max_workers=8)
PY
}

get() { # name
  local name="$1"
  python3 - "$name" <<'PY' | while read -r kind path repo rev; do
import json, sys
name = sys.argv[1]
for d in json.load(open("datasets.lock.json"))["datasets"]:
    if d["name"] == name and d["kind"] != "git-submodule":
        print(d["kind"], d["path"], d.get("repo_id") or d.get("url"), d.get("revision") or "null")
PY
    echo "==> $name -> $path @ $rev"
    case "$kind" in
      huggingface-dataset) hf "$repo" "$rev" "$path" ;;
      skill-snapshot)
        need git
        tmp=$(mktemp -d); trap 'rm -rf "$tmp"' RETURN
        git clone --quiet "$repo" "$tmp/skills"
        git -C "$tmp/skills" checkout --quiet "$rev"
        mkdir -p "$(dirname "$path")"
        # the snapshot is one skill directory out of the monorepo
        cp -r "$tmp/skills"/*/"$name" "$path" 2>/dev/null \
          || cp -r "$tmp/skills/$name" "$path"
        ;;
    esac
  done
}

if [[ "$what" == "all" ]]; then
  for n in Open-SWE-Traces ToolBench TRAIL ha-ultimate; do get "$n"; done
elif [[ "$what" != "submodules" ]]; then
  get "$what"
fi

# ToolBench ships as zips; the tracked layout is the expanded form.
if [[ -f datasets/ToolBench/data.zip ]]; then
  echo "==> expanding ToolBench archives"
  need unzip
  (cd datasets/ToolBench && unzip -q -o data.zip && unzip -q -o reproduction_data.zip \
     && rm -f data.zip reproduction_data.zip)
fi

echo "done."
