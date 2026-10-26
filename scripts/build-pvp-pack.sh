#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo 'Usage: scripts/build-pvp-pack.sh /path/to/Data artifacts/pvp-pack/release [profile.json]' >&2
    exit 2
fi
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$PWD/artifacts/pvp-pack-target}"
cargo build --locked --release --manifest-path tools/pvp-pack/Cargo.toml
"$CARGO_TARGET_DIR/release/wenilla-pvp-pack" build "$1" "${3:-tools/pvp-pack/profile.json}" "$2"
