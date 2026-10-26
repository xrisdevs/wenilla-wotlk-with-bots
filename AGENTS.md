# Agent handoff

## Purpose and branch boundaries

Build a usable WotLK 3.3.5a browser/native client and a strong arena PvP bot platform. `main` is the reusable client + upstream NPCBots server. `arena-with-bots` adds the custom lobby, guest provisioning, preset builds, BotArena and experiments. Put shared browser/protocol fixes on main first, then merge into the arena branch. Do not add arena-only orchestration to main.

## Source of truth

- `sources.json` pins the upstream commits; `scripts/setup-sources.py` restores them without resetting local edits.
- `server/` and `client/benilla-src/` are ignored working trees, **not published sources**. Changes there must be captured into the corresponding patch (relative to the pinned commit) before committing this repo. Include newly added files in that diff; never include target/, tools/, web/dist or runtime data.
- `docker-compose.yml`, `docker/`, and `client/` contain the supported entrypoints.
- On the arena branch, canonical lobby code is `client/lobby/`; `client/prepare-browser.py` stages it. `custom/scripts/BotArena/` and `custom/patch_core.py` are canonical server integration. Avoid independently editing generated copies.

## Working safely

Never commit .env, tokens, cookies, account/character SQL, SQLite state, logs, private endpoints, local absolute paths, game MPQs/DBCs/maps, or build artifacts. Use placeholders in docs and generated local secrets. Scan every file staged for publication, including patch additions and context. Preserve upstream license notices. Do not copy history from private repositories.

Do not reset an existing source tree or delete Docker volumes to make setup pass. Use a clean temporary checkout to check patch restoration. Keep operator SOAP/database interfaces private. Tests must use dedicated accounts and stop only their own matches.

## Validation

Run `python3 scripts/audit-public.py`, Python syntax checks, shell `bash -n`, and `docker compose config --quiet` with a local .env. Restore each source from its exact pin and check patch applicability. For client JS run the restored source's `node --test web/tests/*.test.mjs`; for gateway changes run `cargo test --locked -p wenilla-host`. For engine changes run the relevant Rust tests and build WASM/native as appropriate. Report checks actually run and any untested deployment paths.

Read README.md and docs/ARCHITECTURE.md before changing setup. Maintain branch-specific docs with behavior changes; don't claim the bots have MMR, coordinated CC or competitive quality until implemented and measured.

## Arena branch handoff

Current implementation: guest ownership checks, full-screen Lua lobby, level-80 Season 8 presets, graphical talent/glyph/gear inspection, spectators attached to a bot, preserved manual camera, three-map roster, player/bot queues, crash recovery. Headless benchmarks and tuning utilities are included; no private benchmark output is published. FIFO queues are not MMR. Native desktop supports stock UI and spectator addon; guest provisioning is hosted by the browser lobby.

Validate Python service and tuner tests plus `npm run test:recovery`. Live tests need dedicated guests, initialized preset SQL and the compiled server/client. Check spawns, gate timing, weapon use and camera behavior in a rendered game before claiming visual fixes. Keep source patches, canonical Lua and generated loadout headers in sync.

## PvP server profile

`docker/pvp-server.compose.yml` is opt-in and must use a separate `wenilla-pvp-*` project. Never prune the full database or reuse its active install/build volumes writable. `scripts/prepare-pvp-server.py` requires an empty target; source snapshots stay private. `custom/pvp_core_patches.json` is canonical for runtime guards and is also captured in `patches/server.patch`. Keep battleground dependencies and season/holiday handling; do not assume all quests, transports or creatures are world-only. See `docs/PVP-SERVER.md` for update policy and known validation limits.

## Consolidated arena host

`runtime/arena-host/` is the canonical single-process Docker browser backend. It reuses the ignored source's gateway library through path dependencies; restore sources first. Run `cargo test --locked --manifest-path runtime/arena-host/Cargo.toml` for changes here, plus the rendered lobby/recovery checks when changing the API. Keep the existing SQLite schema/cookie contract compatible; raw tokens and credentials must never enter logs. Python remains for the legacy local and Fly entrypoints, not the default Docker browser runtime. Include `runtime/arena-host` in deployment build change detection, but do not enable the disabled local deployment watcher.

## Dependency-aware PvP assets

`tools/pvp-pack/dependency-profile.json` is opt-in; `profile.json` remains the conservative baseline. `dependencies.rs` owns scenery/audio dependency closure. Keep dynamic character/item/creature/spell families until their runtime filename rules have explicit coverage. Validate every packed byte, run `scripts/check-pvp-closure.py` against the previous pack and rendered request reports, and test all presets (`TEST_ALL_PRESETS=1`) and the three supported arena maps before switching the local preview. Retain the original and prior pack. Do not describe static battleground asset coverage as full battleground gameplay validation.
