# Architecture and branch workflow

```text
Browser (Rust/Bevy WASM, stock FrameXML/Lua)
  HTTP assets + WebSocket game traffic
Rust wenilla-host gateway
  login:3724 -> authserver       world:8085 -> worldserver
                                                |
Native Rust client -----------------------------+ -> MySQL
```

The server is TrinityCore 3.3.5 with NPCBots. The Rust client reads the operator's local MPQ chain. The browser fetches assets through the gateway; the gateway limits TCP forwarding to login/world ports. Standard game login remains on main. Warden is disabled because the experimental client does not implement it.

The two upstream trees are reconstructed from `sources.json`; the browser patch combines the Wenilla platform work with WotLK protocol, UI, rendering, camera and item compatibility fixes. Shared model-preview primitives remain available on main without any arena UI loaded. Native desktop and browser use the same Rust crates. Source history starts fresh in this repo; public upstream attribution is retained separately.

On `arena-with-bots`, a Python aiohttp service owns guest cookies, ordinary game accounts, presets and queues. It proxies the private gateway. Canonical Lua UI is in `client/lobby`; the outer host can replace a crashed WASM iframe and return to the custom lobby. The BotArena C++ module provisions matches and loadouts using core APIs; an addon shows the spectator HUD. Live queues are in memory; guest identity and characters persist.

## Updating sources

Start from a clean pinned checkout. Apply this branch's patch, make changes, run relevant tests, then generate a binary-safe diff against the pin. Mark new source files with `git add -N` before diffing. Review the diff for generated files and secrets. Do not commit an absolute path or alter the upstream revision without revalidating the full patch. Branches apply different server patches; use separate checkouts when switching branches after sources have been restored.

Prefer a shared fix on main followed by a merge into arena-with-bots. Keep arena modules and UI on that branch. Never silently reuse an ignored server tree from the other branch: setup checks the commit, but a no-patch upstream specification cannot undo arena edits.

The shared MPQ reader supports version-2 high table and file offsets, including standalone archives larger than 4 GiB. This is native gateway/desktop functionality; browser asset requests still use HTTP.

## Arena unit APIs

The shared client exposes exact 64-bit `UnitGUID` strings and stable `arena1`–`arena5` / `arenapet1`–`arenapet5` tokens. Arena maps discover hostile player combatants and unowned PvP NPC combatants with playable race descriptors. A slot survives death or temporary visibility loss and is cleared on world transfer or logout. Unit health, power, class, auras, casts and targeting use the same streamed descriptors as normal target frames; hidden objects do not receive fabricated snapshots. `ARENA_OPPONENT_UPDATE`, unit health/power/flag, target, pet, aura and cast events let addons follow changes. Spectator team selection is arena-branch policy, not part of this resolver.

LoadOnDemand addons use the host's directory reader, matching startup addon loading on native and browser builds. Browser addons therefore fetch files under `/addons/` instead of trying to use a nonexistent local filesystem. This makes deferred loading possible once spell data is available; individual addons can still depend on other unimplemented APIs.
