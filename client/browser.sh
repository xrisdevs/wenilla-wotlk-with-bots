#!/usr/bin/env bash
# Build and serve the WotLK arena client locally in a WebGPU browser.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${BENILLA_BROWSER_SOURCE:-$ROOT/client/benilla-src}"
ACTION="${1:-serve}"
case "$ACTION" in
  setup) python3 "$ROOT/scripts/setup-sources.py" benilla; cd "$SRC"; bash scripts/web-setup.sh ;;
  build)
    python3 "$ROOT/client/prepare-browser.py" "$SRC"
    cd "$SRC"
    bash scripts/web-build.sh
    export RUSTC="$(rustup which rustc)"
    export RUSTDOC="$(rustup which rustdoc)"
    rustup run "$(sed -n 's/^channel = "\(.*\)"/\1/p' rust-toolchain.toml)" cargo build --locked --release -p wenilla-host
    ;;
  serve-rust) exec bash "$ROOT/client/serve-arena-host.sh" ;;
  serve)
    test -f "$SRC/web/dist/wenilla_bg.wasm" || { echo 'Run client/browser.sh setup, then client/browser.sh build first.'; exit 1; }
    echo 'Arena browser client: http://127.0.0.1:8090 (WebGPU required)'
    exec bash "$ROOT/client/serve-lobby.sh"
    ;;
  *) echo 'Usage: client/browser.sh setup|build|serve|serve-rust'; exit 2 ;;
esac
