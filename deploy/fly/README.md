# Fly deployment

This is an optional deployment template. Replace `your-arena-app` in both TOML files with your own unique Fly app name and choose your region. The resulting endpoint is `https://YOUR-APP.fly.dev`. One machine runs MySQL, authserver, worldserver, the MPQ/WebSocket gateway and the Python lobby under Supervisor. Only port 8090 is exposed through Fly's HTTPS proxy; MySQL, SOAP, game TCP ports and the gateway bind to loopback.

`fly.toml` provisions 4 shared CPUs and 8 GB RAM. The 40 GB `arena_data` volume stores MySQL, guest sessions, logs, extracted maps and client assets. Automatic volume snapshots are enabled. This is a single-machine deployment: upgrades cause a brief interruption, and queues are not preserved across restarts. Do not scale it to multiple machines without splitting out shared database/session/matchmaking state.

## Build and deploy

1. For a first deployment, create the app and volume (`fly apps create your-arena-app`, `fly volumes create arena_data --region lhr --size 40 --yes`), then run `fly deploy --config deploy/fly/bootstrap.toml --remote-only --ha=false` to start a private staging machine. Upload the complete client `Data` directory to `/persist/game-data` and extracted TrinityCore data to `/persist/server-data` using `fly ssh sftp put`. Verify the uploads, then create `.ready` inside both directories. `verify_assets.py` can verify all client files against a SHA-256 manifest before creating that marker. The startup script refuses to initialize without these markers. Allocate a shared IPv4 and an IPv6 address before the first public deployment.
2. Restore and build the browser using `client/browser.sh setup` and `client/browser.sh build`.
3. Run `python3 deploy/fly/prepare.py` while the local Docker database is running. This stages the tested WASM bundle and database seeds under ignored `artifacts/fly/`. Auth and character seeds contain schema/reference data only; they do not copy local users, credentials, characters or browser cookies. World data includes the arena gear presets and NPCBot templates.
4. Set `ARENA_DB_PASSWORD` and `ARENA_SOAP_PASS` with `fly secrets import --stage`. Use independent random alphanumeric values of at least 32 characters. Never put them in Git or command-line arguments. The startup script creates/updates the private `ARENAOP` operator account from these secrets.
5. Run `fly deploy --remote-only --ha=false`. The Dockerfile restores pinned sources, applies this repository's patches/custom scripts, compiles Linux server/gateway binaries, and packages the staged browser bundle. Existing database and guest state are retained on redeploy; seed SQL is imported only when `/persist/.database-ready` is absent.
6. Verify `curl -f https://your-arena-app.fly.dev/healthz`, then run `BROWSER_URL=https://your-arena-app.fly.dev node client/check-lobby.cjs` for the rendered game flow.

SQL seeds are only for first initialization. Apply subsequent schema/data migrations deliberately before enabling features that need them; automatic TrinityCore database updates are disabled because the initial seeds already contain the current applied updates.

## Operations

- `fly status` / `fly checks list` / `fly logs`
- `fly ssh console -C 'tail -100 /persist/logs/Server.log'`
- `fly volumes list` / `fly volumes snapshots list <volume-id>`
- `fly machine restart <machine-id>` gracefully restarts the stack.

`/healthz` checks the login, world and gateway listeners plus an authenticated database query. The lobby uses its configured `ARENA_PUBLIC_ORIGIN` for HTTPS cookie and origin checks. Game data and WebSocket routes require a valid guest cookie. The game gateway is kept private behind this session boundary.

Changing the hostname requires updating `ARENA_PUBLIC_ORIGIN` and configuring that hostname's Fly certificate. Clearing a browser's guest cookie loses access to that guest's heroes. Keep the persistent SQLite guest state and MySQL state together when restoring backups.
