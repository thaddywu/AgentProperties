#!/usr/bin/env bash
set -euo pipefail
nova_root="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$nova_root/grokbot/scripts/nova-demo.sh" "$@"
