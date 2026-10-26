#!/usr/bin/env bash
set -euo pipefail
wenilla-host --bind 127.0.0.1:8092 --www /www --data /game-data --upstream authserver --world-upstream worldserver &
gateway=$!
/opt/venv/bin/python /app/controller/lobby/service.py --bind "${ARENA_BIND:-0.0.0.0}" --port "${ARENA_PORT:-8090}" &
lobby=$!
trap 'kill "$gateway" "$lobby" 2>/dev/null || true; wait || true' EXIT
trap 'exit 0' TERM INT
wait -n "$gateway" "$lobby"
