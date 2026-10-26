#!/usr/bin/env bash
# Single-process native host. Database access must be explicitly configured.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
umask 077
: "${ARENA_DB_HOST:?Set ARENA_DB_HOST to a reachable private database host}"
: "${ARENA_DB_PASSWORD:?Set ARENA_DB_PASSWORD}"
: "${ARENA_SOAP_PASS:?Set ARENA_SOAP_PASS}"
export ARENA_PUBLIC_ORIGIN="${ARENA_PUBLIC_ORIGIN:-http://localhost:8090}"
export WOW_DATA="${WOW_DATA:?Set WOW_DATA to your Data directory or PvP MPQ}"
export ARENA_WWW="${ARENA_WWW:-$ROOT/client/benilla-src/web/dist}"
export ARENA_LOBBY_UI="${ARENA_LOBBY_UI:-$ROOT/client/lobby}"
export ARENA_BUILDS="${ARENA_BUILDS:-$ROOT/controller/lobby/builds.json}"
export ARENA_LOBBY_HOME="${ARENA_LOBBY_HOME:-$ROOT/artifacts/lobby/state}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$ROOT/artifacts/arena-host-target}"
cargo build --locked --release --manifest-path runtime/arena-host/Cargo.toml
exec "$CARGO_TARGET_DIR/release/wenilla-arena-host"
