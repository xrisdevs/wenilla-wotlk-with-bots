# Wenilla WotLK with Bots

A browser and native Rust client for **World of Warcraft 3.3.5a (build 12340)**, paired with a Dockerized TrinityCore server and NPCBots. The goal is to build proper arena play and increasingly capable PvP bots, with repeatable matches and measurements guiding improvements.

This is an experimental development project. It builds on [Benilla-WotLK](https://github.com/Onixaz/benilla-wotlk), [Wenilla](https://github.com/Arnesen/wenilla), and [TrinityCore with NPCBots](https://github.com/trickerer/TrinityCore-3.3.5-with-NPCBots). Browser rendering uses Rust/Bevy compiled to WebAssembly and WebGPU; a small Rust gateway serves assets and translates WebSockets to the game protocol.

| Branch | Purpose |
| --- | --- |
| **main** | Standard game login/UI, browser + native clients, upstream NPCBots server. Shared rendering, protocol and model-preview fixes live here. |
| [arena-with-bots](https://github.com/xrisdevs/wenilla-wotlk-with-bots/tree/arena-with-bots) | Custom in-game lobby, guest accounts, Season 8 presets, spectating, bot/human arenas, matchmaking and PvP bot experiments. |

No Blizzard game assets, account databases, credentials or build outputs are included. Supply your own English 3.3.5a `Data` directory; Docker fetches the pinned TrinityCore world database automatically. Upstream sources are pinned in `sources.json` and restored with patches; they are intentionally not copied into this Git history.

## Requirements

- Docker Engine/Desktop with Compose v2; allow at least 8 GB RAM (more for parallel builds) and ample disk for source builds and your game data.
- Git and Python 3.10+ for setup. Rust via rustup and a C compiler only if building the client outside Docker.
- A WebGPU-capable Chrome/Edge browser. Localhost works over HTTP; remote browser access requires HTTPS.
- Your own English WoW 3.3.5a game data. You do not need to run the original WoW executable. Docker downloads the pinned TDB335 database from its official release.

## Run everything with Docker

```sh
git clone https://github.com/xrisdevs/wenilla-wotlk-with-bots.git
cd wenilla-wotlk-with-bots
python3 scripts/init-env.py
# Edit .env: WOW_CLIENT_DIR must be the absolute directory containing Data/.
python3 scripts/setup-sources.py all
docker compose --profile build build build
docker compose --profile build run --rm build
docker compose --profile extract run --rm extract
docker compose up -d db authserver worldserver
docker compose logs -f worldserver
# Wait for the initial world import and database updates to finish.
docker compose --profile browser up -d --build browser
```

Open **http://localhost:8090**. The standard game login screen appears. Create a normal account through the worldserver console: `docker compose attach worldserver`, then enter `account create YOURNAME YOURPASSWORD`. Detach using Ctrl-P, Ctrl-Q; Ctrl-C stops the server. Keep operator accounts separate from ordinary players. Default realm address is loopback, suitable for local desktop use; browser world connections are routed through the gateway.

Worldserver startup automatically downloads **TDB335.26091**, verifies SHA-256 for both the archive and extracted SQL, and caches it in `tdb-cache`. No separate setup container is created. The worldserver waits for verification and imports the seed only when its world database needs initialization; existing databases are not reset. See [database setup](docs/DATABASE.md).

The extract job generates maps, DBCs, vmaps and arena mmaps. Set `MMAP_MAPS=all` in `.env` and rerun it to generate navigation for the full world (can take hours). The initial C++ and Rust/WASM builds are substantial; later server builds reuse Docker volumes. Startup imports NPCBots base tables through the upstream database updater.

All exposed ports bind to loopback. Database credentials are generated into ignored `.env`; no shared administrator account is created. Persistent state lives in Compose volumes. `docker compose down` retains it; **`down -v` deletes it**.

## Browser client built locally

With the Docker server running, install rustup and a C compiler (Xcode Command Line Tools on macOS; build-essential/clang/pkg-config on Linux):

```sh
bash client/browser.sh setup
bash client/browser.sh build
WOW_DATA=/absolute/path/to/WoW_3.3.5a/Data bash client/browser.sh serve
```

Stop the Compose browser service first if it occupies port 8090. Setup installs the source tree's pinned Rust toolchain, matching wasm-bindgen, WASI SDK and Binaryen. The page uses the ordinary game login; credentials in query strings are disabled. Display defaults are 1080p/high quality with device-pixel-ratio-aware pointer mapping.

## Native desktop client (Rust)

```sh
python3 scripts/setup-sources.py benilla
cd client/benilla-src
cargo build --locked --profile play -p benilla
cd ../..
WOW_DATA=/absolute/path/to/WoW_3.3.5a/Data bash client/benilla.sh
```

macOS needs Xcode Command Line Tools. Linux also needs ALSA/udev development packages (`libasound2-dev libudev-dev pkg-config` on Ubuntu). Native Windows requires the Rust MSVC toolchain and Visual Studio build tools; run `cargo play` inside the restored source with `WOW_DATA` set in PowerShell. The shell launchers target Linux/macOS. Native client settings stay under ignored `artifacts/desktop` by default. Optional `WOW_HOST`, `WOW_USER`, `WOW_PASS` and `WOW_CHAR` environment variables configure a server or unattended login; never commit them.

## Deployment and development

See [deployment](docs/DEPLOYMENT.md), [architecture and branch workflow](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md) and [agent instructions](AGENTS.md). The arena branch documents its native WoW lobby and persistent all-in-one Docker/Fly deployment separately.

Licensing is component-specific: new integration code is MIT; client-derived changes retain MIT/Apache-2.0 terms; TrinityCore/NPCBots-derived changes retain GPL terms. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY.md). Game assets and trademarks belong to their respective owners and are not covered by these source-code licenses.
