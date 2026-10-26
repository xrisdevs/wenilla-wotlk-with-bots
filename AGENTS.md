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
