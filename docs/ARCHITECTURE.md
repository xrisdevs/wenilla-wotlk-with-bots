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

On `arena-with-bots`, the Docker browser service is one `wenilla-arena-host` Rust process. It owns guest cookies, ordinary game accounts, presets and queues, and mounts the existing asset and WebSocket routers directly. SQLx maintains a small MySQL connection pool and opens the existing private SQLite guest state; no Python HTTP proxy or per-request MySQL CLI is involved. The Python service remains available for legacy local/Fly launchers. Canonical Lua UI is in `client/lobby`; the outer host can replace a crashed WASM iframe and return to the custom lobby. The BotArena C++ module provisions matches and loadouts using core APIs; an addon shows the spectator HUD. Live queues are in memory; guest identity and characters persist.

## Updating sources

Start from a clean pinned checkout. Apply this branch's patch, make changes, run relevant tests, then generate a binary-safe diff against the pin. Mark new source files with `git add -N` before diffing. Review the diff for generated files and secrets. Do not commit an absolute path or alter the upstream revision without revalidating the full patch. Branches apply different server patches; use separate checkouts when switching branches after sources have been restored.

Prefer a shared fix on main followed by a merge into arena-with-bots. Keep arena modules and UI on that branch. Never silently reuse an ignored server tree from the other branch: setup checks the commit, but a no-patch upstream specification cannot undo arena edits.

The shared MPQ reader supports version-2 high table and file offsets, including standalone archives larger than 4 GiB. This is native gateway/desktop functionality; browser asset requests still use HTTP.

See [runtime consolidation](RUNTIME.md) for configuration, rollback and remaining service boundaries.
