#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${WOW_DATA:?Set WOW_DATA to your WotLK Data directory}"
export WOW_HOST="${WOW_HOST:-127.0.0.1:3724}"
export BENILLA_HOME="${BENILLA_HOME:-$ROOT/artifacts/desktop}"
mkdir -p "$BENILLA_HOME"
python3 "$ROOT/client/configure-display.py" "$BENILLA_HOME/config.toml"
export WOW_DPI=1 WOW_UI_SCALE=1 WOW_MSAA=8
unset WOW_WIN
mkdir -p "$BENILLA_HOME/AddOns"
python3 "$ROOT/client/install-addons.py" "$BENILLA_HOME/AddOns"
exec "$ROOT/client/benilla-src/target/play/benilla"
