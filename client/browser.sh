#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/client/benilla-src"
case "${1:-serve}" in
 setup) python3 "$ROOT/scripts/setup-sources.py" benilla; cd "$SRC"; bash scripts/web-setup.sh ;;
 build) python3 "$ROOT/client/prepare-browser.py" "$SRC"; cd "$SRC"; bash scripts/web-build.sh; cargo build --locked --release -p wenilla-host ;;
 serve)
   : "${WOW_DATA:?Set WOW_DATA to your WotLK Data directory}"
   exec "$SRC/target/release/wenilla-host" --bind "${WEB_BIND:-127.0.0.1:8090}" --www "$SRC/web/dist" --data "$WOW_DATA" --upstream "${WOW_HOST:-127.0.0.1}" ;;
 *) echo 'Usage: client/browser.sh setup|build|serve'; exit 2 ;;
esac
