#!/usr/bin/env bash
set -euo pipefail
nova_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$nova_root"
# Native Soufflé is pinned in Dockerfile.nova; evaluations run locally.
nova_image="${NOVA_IMAGE:-rakazo:nova-souffle}"
nova_port="${NOVA_PORT:-5180}"
nova_container="${NOVA_CONTAINER:-nova-reasoning-demo}"
nova_volume="${NOVA_STATE_VOLUME:-nova-reasoning-state}"
mode="${1:-restart}"
mounts=(--volume "$nova_root/packages/core/package.json:/app/packages/core/package.json:ro" --volume "$nova_root/packages/core/src:/app/packages/core/src" --volume "$nova_root/apps/web/src:/app/apps/web/src" --volume "$nova_root/apps/web/nova.html:/app/apps/web/nova.html:ro" --volume "$nova_root/apps/web/vite.nova.config.ts:/app/apps/web/vite.nova.config.ts:ro")
health() {
  docker exec -i "$nova_container" node --input-type=module <<'JS'
const base = "http://127.0.0.1:5180";
try {
  const page = await fetch(base + "/", { signal: AbortSignal.timeout(3000) });
  if (!page.ok || !(await page.text()).includes("/src/features/nova/main.tsx")) throw new Error("Nova page is unavailable");
  async function api(body) {
    const response = await fetch(base + "/nova-api", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
    return data.result;
  }
  const state = await api({ operation: "state" });
  const query = await api({ operation: "query", revision: state.version, query: "?- Auditor(A)." });
  console.log(`Healthy: Nova page + runtime API + Datalog query (${query.rows.length} rows)`);
  console.log(`Saved state: revision ${state.version}, ${state.messages.length} messages, ${state.records.length} input facts`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
JS
}
case "$mode" in
  setup) exec docker build -t "$nova_image" -f infra/compose/Dockerfile.nova . ;;
  test) exec docker run --rm --network none --user 0 "${mounts[@]}" "$nova_image" /app/node_modules/.bin/vitest run packages/core/src/policy/reasoning packages/core/src/policy/query.test.ts packages/core/src/policy/protocol.test.ts ;;
  check) exec docker run --rm --network none --user 0 "${mounts[@]}" "$nova_image" /app/node_modules/.bin/tsc --noEmit -p /app/apps/web/tsconfig.json ;;
  build) exec docker run --rm --network none --user 0 "${mounts[@]}" --workdir /app/apps/web "$nova_image" /app/apps/web/node_modules/.bin/vite build --config vite.nova.config.ts ;;
  logs) exec docker logs --tail 80 --follow "$nova_container" ;;
  status)
    docker inspect --format 'Container: {{.Name}} | status: {{.State.Status}} | started: {{.State.StartedAt}}' "$nova_container"
    health ;;
  stop) exec docker stop --time 5 "$nova_container" ;;
  restart|start|serve)
    echo '[1/4] Checking Docker and the Soufflé image...'
    docker info >/dev/null
    if ! docker image inspect "$nova_image" >/dev/null 2>&1; then
      docker build -t "$nova_image" -f infra/compose/Dockerfile.nova .
    fi
    echo "[2/4] Replacing $nova_container; keeping saved state in $nova_volume..."
    if docker container inspect "$nova_container" >/dev/null 2>&1; then
      docker stop --time 5 "$nova_container" >/dev/null
      # Older launchers used --rm, so stopping may already remove the container.
      nova_remove_deadline=$((SECONDS + 15))
      while docker container inspect "$nova_container" >/dev/null 2>&1; do
        if docker rm "$nova_container" >/dev/null 2>&1; then break; fi
        if ((SECONDS >= nova_remove_deadline)); then
          echo "Could not remove stopped container $nova_container." >&2
          exit 1
        fi
        sleep 1
      done
    fi
    echo "[3/4] Starting frontend + policy worker on port $nova_port..."
    if ! docker run --detach --init --restart unless-stopped --user 0 --name "$nova_container" \
      --volume "$nova_volume:/nova-state" --env NOVA_STATE_FILE=/nova-state/runtime.json \
      -p "127.0.0.1:$nova_port:5180" "${mounts[@]}" --workdir /app/apps/web \
      "$nova_image" /app/apps/web/node_modules/.bin/vite --config vite.nova.config.ts --host 0.0.0.0 >/dev/null; then
      echo 'Startup failed. Check the Docker error above (for example, a port conflict).' >&2
      exit 1
    fi
    echo '[4/4] Checking page, runtime and an executable Datalog query...'
    nova_deadline=$((SECONDS + 40))
    until nova_health="$(health 2>&1)"; do
      if ((SECONDS >= nova_deadline)) || [[ "$(docker inspect --format '{{.State.Running}}' "$nova_container")" != true ]]; then
        echo "Health check failed: $nova_health" >&2
        docker logs --tail 80 "$nova_container" >&2
        exit 1
      fi
      echo "  Waiting: $nova_health"
      sleep 1
    done
    echo "$nova_health"
    docker exec "$nova_container" souffle --version | head -n 3
    docker logs --tail 8 "$nova_container"
    echo "Ready: http://127.0.0.1:$nova_port/"
    echo 'Runs in the background; closing this terminal will not stop it.'
    echo 'Commands: ./nova-demo.sh [restart|status|logs|stop]'
    if [[ "$mode" == serve ]]; then exec docker logs --tail 20 --follow "$nova_container"; fi
    ;;
  *) echo 'Usage: ./nova-demo.sh [restart|start|serve|status|logs|stop|setup|test|check|build]' >&2; exit 2 ;;
esac
