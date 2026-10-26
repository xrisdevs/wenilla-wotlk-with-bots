#!/usr/bin/env bash
# Sync custom scripts into the vendored core tree and apply the core patches (idempotent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/server/src/server/scripts/Custom/BotArena"
cp -f "$ROOT"/custom/scripts/BotArena/*.{cpp,h} "$ROOT/server/src/server/scripts/Custom/BotArena/"
python3 "$ROOT/custom/patch_core.py"
