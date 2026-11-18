#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo 'Usage: ./install.sh [--provider both|openai|anthropic|codex-compatible-local-endpoint|none]'
  echo 'Prepare the Python environment, native tools and Docker images. No API key is needed.'
}

provider=both
while (($#)); do
  case "$1" in
    --provider)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      provider=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
case "$provider" in
  both|openai|anthropic|codex-compatible-local-endpoint|none) ;;
  *) usage >&2; exit 2 ;;
esac

fail() { echo "$* See docs/setup.md for manual installation." >&2; exit 1; }
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail 'Automatic setup currently supports Linux x86_64.'
command -v python3 >/dev/null || fail 'Install Python 3.10 or newer first.'
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail 'Python 3.10 or newer is required.'
command -v docker >/dev/null || fail 'Install Docker first.'
docker info >/dev/null 2>&1 || fail 'Start Docker and enable access for your user.'

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$root"

# Only request system installation for missing prerequisites; leave Docker access
# and existing package repositories under the user's control.
packages=()
if command -v dpkg-query >/dev/null; then
  for package in git ca-certificates dpkg util-linux libffi8 libgomp1 libncurses6 libtinfo6 libsqlite3-0 libstdc++6 libgcc-s1 zlib1g; do
    if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]]; then
      packages+=("$package")
    fi
  done
else
  fail 'Install the Ubuntu/Debian system prerequisites listed in the manual instructions.'
fi
if [[ ! -x .venv/bin/python ]] && ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  packages+=(python3-venv)
fi
if ((${#packages[@]})); then
  command -v apt-get >/dev/null || fail 'Install the missing system prerequisites.'
  admin=()
  if ((EUID != 0)); then
    command -v sudo >/dev/null || fail 'Administrator access is needed for missing system packages.'
    admin=(sudo)
  fi
  "${admin[@]}" apt-get update
  "${admin[@]}" apt-get install -y --no-install-recommends "${packages[@]}"
fi

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
export PATH="$root/.venv/bin:$HOME/.local/bin:$PATH"
fingerprint=$(sha256sum pyproject.toml | cut -d ' ' -f 1)
marker=.venv/.policyweave-install
if [[ ! -f $marker || $(cat "$marker") != "$fingerprint" ]] || ! .venv/bin/python -c 'import yaml, mcp, policyweave' 2>/dev/null; then
  .venv/bin/python -m pip install -e '.[mcp]'
  echo "$fingerprint" > "$marker"
fi
.venv/bin/python -B -m policyweave.adapters.install_tools --provider "$provider"

docker build -f src/policyweave/adapters/Dockerfile -t policy-portin:local .
docker build -f src/policyweave/adapters/Dockerfile.batch -t policy-portin:batch-v1 .
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp --entrypoint python policy-portin:batch-v1 -c 'import yaml, mcp; from policyweave.core.datalog import Souffle, parse; rules, _ = parse("Ready(X) :- Probe(X)."); assert Souffle().evaluate([{"predicate":"Probe","args":["c:ready"]}], rules); print("Container dependencies and engine ready")'
echo 'Installation complete. Activate with: source .venv/bin/activate'
