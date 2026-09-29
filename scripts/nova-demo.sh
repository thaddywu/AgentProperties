#!/usr/bin/env bash
set -euo pipefail
nova_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$nova_root"
# Reuse the already installed local Rakazo image; no package downloads or model calls.
nova_image="${NOVA_IMAGE:-rakazo:policy-local}"
nova_port="${NOVA_PORT:-5180}"
mode="${1:-serve}"
mounts=(--volume "$nova_root/packages/core/package.json:/app/packages/core/package.json:ro" --volume "$nova_root/packages/core/src:/app/packages/core/src" --volume "$nova_root/apps/web/src:/app/apps/web/src" --volume "$nova_root/apps/web/nova.html:/app/apps/web/nova.html:ro" --volume "$nova_root/apps/web/vite.nova.config.ts:/app/apps/web/vite.nova.config.ts:ro")
case "$mode" in
  test) exec docker run --rm --network none --user 0 "${mounts[@]}" "$nova_image" /app/node_modules/.bin/vitest run packages/core/src/policy/reasoning packages/core/src/policy/query.test.ts packages/core/src/policy/protocol.test.ts ;;
  check) exec docker run --rm --network none --user 0 "${mounts[@]}" "$nova_image" /app/node_modules/.bin/tsc --noEmit -p /app/apps/web/tsconfig.json ;;
  build) exec docker run --rm --network none --user 0 "${mounts[@]}" --workdir /app/apps/web "$nova_image" /app/apps/web/node_modules/.bin/vite build --config vite.nova.config.ts ;;
  serve) echo "Nova demo: http://127.0.0.1:$nova_port/nova.html"; exec docker run --rm --user 0 --name nova-reasoning-demo -p "127.0.0.1:$nova_port:5180" "${mounts[@]}" --workdir /app/apps/web "$nova_image" /app/apps/web/node_modules/.bin/vite --config vite.nova.config.ts --host 0.0.0.0 ;;
  *) echo 'Usage: scripts/nova-demo.sh [serve|test|check|build]' >&2; exit 2 ;;
esac
