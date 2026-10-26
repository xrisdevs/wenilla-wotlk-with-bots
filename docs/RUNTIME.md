# Consolidated arena runtime

The arena branch's Docker browser service runs one native `wenilla-arena-host` executable. It serves the lobby, browser WASM/static files, MPQ reads, authenticated game WebSockets, guest provisioning, queues and crash-recovery API. The existing client and combat engine are unchanged.

Previously every asset and game socket crossed a Python proxy into a separate Rust gateway. Database queries spawned the MySQL CLI. The Rust host mounts the gateway library directly and uses four pooled MySQL connections plus a SQLite worker connection. The final Docker image contains neither Python nor the MySQL CLI; build-time tools stay in the build stage.

## What remains separate

- TrinityCore authserver and worldserver still implement the game protocol and combat.
- MySQL still stores auth, character and reduced world data.
- The private `lobby-data` volume still contains `guests.sqlite` using the previous schema. Cookies, account ownership, prepared heroes and passwords retain their existing format. Queues and current lobby statuses remain in memory and are cleared on restart.
- Game assets remain operator-supplied external files, optionally the standalone PvP MPQ. No assets or player data are embedded in the executable.

This is a consolidation of the browser backend, not a rewritten combat engine or removal of MySQL. It removes processes and a network relay; no frame-rate or combat-throughput gain is claimed without measurements.

## Build and run

The normal Docker instructions in the README now build this runtime. No extra service or migration is required. The same image works with the isolated [PvP profile](PVP-SERVER.md) and [PvP pack overlay](PVP-ASSETS.md).

To compile just the host after restoring sources:

```sh
cargo test --locked --manifest-path runtime/arena-host/Cargo.toml
cargo build --locked --release --manifest-path runtime/arena-host/Cargo.toml
```

Rust 1.89 or newer and a C compiler are required. SQLx builds bundled SQLite. The source's pinned rustup toolchain is used in the Docker build.

For a native host, first build the browser bundle with `client/browser.sh build`, then set these environment variables privately:

- `WOW_DATA`: a Data directory or a standalone MPQ.
- `ARENA_DB_HOST`, `ARENA_DB_PORT` (default 3306), `ARENA_DB_USER` (default trinity), `ARENA_DB_PASSWORD`: a reachable private MySQL endpoint.
- `ARENA_SOAP_URL`, `ARENA_SOAP_USER`, `ARENA_SOAP_PASS`: the private operator endpoint.
- `ARENA_LOGIN_HOST`, `ARENA_WORLD_HOST`: game servers (default loopback).
- `ARENA_PUBLIC_ORIGIN`: the exact browser origin, including port, for example `http://localhost:8090`.

Run `bash client/browser.sh serve-rust`. The launcher defaults to loopback, port 8090, and private state under `artifacts/lobby/state`. It does not expose the Compose database or create a tunnel automatically. Docker's internal network supplies these connections without publishing MySQL. `serve` remains the older Python launcher for local setups without direct DB access. The legacy Fly packaging is also unchanged; it has not been migrated or redeployed.

Optional paths: `ARENA_WWW`, `ARENA_LOBBY_UI`, `ARENA_BUILDS`, `ARENA_LOBBY_HOME`. `ARENA_BIND` and `ARENA_PORT` control the listener. All mutating actions and credentials enforce the configured origin; game assets and sockets require a valid guest cookie. `/healthz` checks the database, guest state and game listeners. SOAP/database errors return generic failures rather than credentials or connection strings.

## State and rollback

Use the same `lobby-data` volume when switching between the old and new images. Stop the old browser service first; run only one queue coordinator against a guest database. No destructive schema migration occurs. Recreating the browser service clears in-memory queues; the browser can recover/reconnect using its existing cookie. Keep the prior image tag for rollback and recreate only `browser`, preserving all volumes.

The PvP preparation script uses a short-lived Python helper for a consistent read-only SQLite backup; Python is no longer required inside the browser container. That helper exits and is removed automatically.

## Verification

Unit checks cover the SRP reference vector, guest-state compatibility, ownership/loadout validation, direct and nested gateway authorization, cross-origin boundaries, SOAP result parsing and healer-balanced queue ordering. Validate rendered character selection, tooltips, spectating, bot participation, queue cancellation and recovery against an isolated stack before deployment. Do not publish production guest databases or test cookies.

### Local measurement

The isolated preview's browser image decreased from 139,387,471 to 104,628,782 bytes as reported by Docker (about 25%). The runtime executable is about 10.4 MiB, and the container has one long-running process. These image measurements reuse the same existing WASM bundle; the native Linux host and final runtime image were rebuilt. They exclude the external MPQ, game database and server data volumes. No full WASM rebuild or cloud rollout was needed for this check.

To repeat the rendered check on the isolated stack:

```sh
BROWSER_URL=http://localhost:8096 TEST_WIDTH=1920 TEST_HEIGHT=1080 npm run test:lobby
npm run test:recovery
```

The old full stack and cloud deployment remain separate from the opt-in PvP preview. Further consolidation still needs to address TrinityCore's dependency on MySQL before claiming a self-contained game server.

The local verification passed eight Rust host tests, the existing gateway/browser/recovery checks, and the complete 1920×1080 rendered lobby flow (inspection, rotation, spectating, bot participation, queue cancellation and saved-hero switching). Live API checks also verified cross-guest isolation, recovery, persistent identity after restart and the read-only backup helper. All 3,395 successful asset paths captured during this run were present in the reduced MPQ manifest. This does not establish full battleground coverage, real multi-player matchmaking under load or resolution of the previously observed long-session disconnects.
