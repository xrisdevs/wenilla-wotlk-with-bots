#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${BENILLA_BROWSER_SOURCE:-$ROOT/client/benilla-src}"
PY="$ROOT/artifacts/lobby/venv/bin/python"
if [ ! -x "$PY" ]; then
  python3 -m venv "$ROOT/artifacts/lobby/venv"
  "$PY" -m pip install -r "$ROOT/controller/lobby/requirements.txt"
fi
python3 "$ROOT/client/prepare-browser.py" "$SRC"
cp "$SRC/web/index.html" "$SRC/web/arena-display.js" "$SRC/web/game-session.js" "$SRC/web/dist/"
# Refresh sidecars as well as plaintext, so cached builds never serve an older bootstrap.
for ASSET in arena-display.js game-session.js; do
  if command -v brotli >/dev/null; then
    brotli -f -q 5 "$SRC/web/dist/$ASSET"
  else
    python3 -c 'import pathlib,sys; pathlib.Path(sys.argv[1]).unlink(missing_ok=True)' "$SRC/web/dist/$ASSET.br"
  fi
  gzip -kf -6 "$SRC/web/dist/$ASSET"
done
cp -R "$SRC/web/addons/." "$SRC/web/dist/addons/"
"$SRC/target/release/wenilla-host" --bind 127.0.0.1:8092 --www "$SRC/web/dist" --data "${WOW_DATA:-$HOME/wow-client-data/Data}" --upstream "${WOW_HOST:-127.0.0.1}" &
GATEWAY_PID=$!
trap 'kill "$GATEWAY_PID" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
"$PY" "$ROOT/controller/lobby/service.py" --bind "${ARENA_BIND:-127.0.0.1}" --port "${ARENA_PORT:-8090}"
