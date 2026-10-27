# Wenilla WotLK with Bots — Arena

A browser and native Rust client for **World of Warcraft 3.3.5a (build 12340)**, paired with a Dockerized TrinityCore server and NPCBots. The goal is to build proper arena play and increasingly capable PvP bots, with repeatable matches and measurements guiding improvements.

This is an experimental development project. It builds on [Benilla-WotLK](https://github.com/Onixaz/benilla-wotlk), [Wenilla](https://github.com/Arnesen/wenilla), and [TrinityCore with NPCBots](https://github.com/trickerer/TrinityCore-3.3.5-with-NPCBots). Browser rendering uses Rust/Bevy compiled to WebAssembly and WebGPU; a small Rust gateway serves assets and translates WebSockets to the game protocol.

| Branch | Purpose |
| --- | --- |
| **main** | Standard game login/UI, browser + native clients, upstream NPCBots server. Shared rendering, protocol and model-preview fixes live here. |
| [arena-with-bots](https://github.com/xrisdevs/wenilla-wotlk-with-bots/tree/arena-with-bots) | Custom in-game lobby, guest accounts, Season 8 presets, spectating, bot/human arenas, matchmaking and PvP bot experiments. |

This branch includes the full-screen native WoW lobby, drag-to-rotate hero preview, graphical talent trees, equipment/glyph tooltips, Season 8 loadouts, bot-only spectating, solo or two-friend human-versus-bot play, varied bot opponents, separate 2v2/3v3 player queues, and client-crash recovery back to the lobby. Camera selection preserves the view you leave it in. Nagrand, Blade’s Edge and Lordaeron are enabled in the random roster; Dalaran is excluded. Player matchmaking is currently unrated FIFO.

No Blizzard game assets, account databases, credentials or build outputs are included. Supply your own English 3.3.5a `Data` directory; Docker fetches the pinned TrinityCore world database automatically. Upstream sources are pinned in `sources.json` and restored with patches; they are intentionally not copied into this Git history.

## Requirements

- Docker Engine/Desktop with Compose v2; allow at least 8 GB RAM for runtime; browser source builds need additional memory (12 GB or more recommended) and ample disk for source builds and your game data.
- Git and Python 3.10+ for setup. Rust via rustup and a C compiler only if building the client outside Docker.
- A WebGPU-capable Chrome/Edge browser. Localhost works over HTTP; remote browser access requires HTTPS.
- Your own English WoW 3.3.5a game data. You do not need to run the original WoW executable. Docker downloads the pinned TDB335 database from its official release.

## Run everything with Docker

```sh
git clone https://github.com/xrisdevs/wenilla-wotlk-with-bots.git
cd wenilla-wotlk-with-bots
git switch arena-with-bots
python3 scripts/init-env.py
# Edit .env: WOW_CLIENT_DIR must be the absolute directory containing Data/.
python3 scripts/setup-sources.py all
bash scripts/apply-custom.sh
docker compose --profile build build build
docker compose --profile build run --rm build
docker compose --profile extract run --rm extract
docker compose up -d db authserver worldserver
docker compose logs -f worldserver
# Wait for the initial world import and database updates to finish.
python3 scripts/init-arena.py
docker compose restart worldserver
docker compose --profile browser up -d --build browser
```

Open **http://localhost:8090**. The game loads first, then shows the custom lobby. Each browser receives its own guest identity. Choose **Watch**, **Bots**, or **Players**; select a prebuilt hero and an optional name for playable modes. A player-only 2v2/3v3 queue needs four/six humans; it never silently fills with bots.

To team up, both players choose **Play with bots → With a friend** and the same format. One clicks **New code** and shares the eight-character code; the other enters it. Both choose a hero and click **Enter Arena**. The first waits for the second in the game UI. In 2v2, your two heroes face two bots; in 3v3, one allied bot fills your third slot. Create a fresh code for the next match. Codes are temporary and consumed when a match starts; leaving or disconnecting removes your waiting slot. Use separate browser profiles/devices for separate guest identities.

Bot opponents rotate through four 2v2 and twelve 3v3 preset compositions, excluding the immediately previous lineup for that format. Solo play uses the same opponent pool. This is composition variety, not difficulty or skill-based matchmaking.

`init-arena.py` creates/updates a separate private operator using `.env`, and imports the supplied gear preset tables. Run it after initial setup or intentional preset changes, not as an automatic migration against a populated production world. Do not use the operator to play. Guest identity persists in the `lobby-data` volume; clearing browser cookies loses access to that guest's heroes.

Worldserver startup automatically downloads **TDB335.26091**, verifies SHA-256 for both the archive and extracted SQL, and caches it in `tdb-cache`. No separate setup container is created. The worldserver waits for verification and imports the seed only when its world database needs initialization; existing databases are not reset. See [database setup](docs/DATABASE.md).

The extract job generates maps, DBCs, vmaps and arena mmaps. Set `MMAP_MAPS=all` in `.env` and rerun it to generate navigation for the full world (can take hours). If WASM packaging is killed for lack of memory, stop the running game stack before building or raise Docker’s memory allowance. Rust build outputs are cached across retries. The initial C++ and Rust/WASM builds are substantial; later server builds reuse Docker volumes. Startup imports NPCBots base tables through the upstream database updater.

All exposed ports bind to loopback. Database and private operator credentials are generated into ignored `.env`; no shared default password is used. Persistent state lives in Compose volumes. `docker compose down` retains it; **`down -v` deletes it**.

## Browser client built locally

With the Docker server running, install rustup and a C compiler (Xcode Command Line Tools on macOS; build-essential/clang/pkg-config on Linux):

```sh
bash client/browser.sh setup
bash client/browser.sh build
export ARENA_SOAP_USER=ARENAOP
# Set ARENA_SOAP_PASS in your environment to the generated value in .env.
WOW_DATA=/absolute/path/to/WoW_3.3.5a/Data bash client/browser.sh serve
```

Stop the Compose browser service first if it occupies port 8090. Setup installs the source tree's pinned Rust toolchain, matching wasm-bindgen, WASI SDK and Binaryen. This legacy local launcher runs the Python lobby on 8090 and its private Rust gateway on 8092. Docker uses the consolidated Rust host; `bash client/browser.sh serve-rust` runs the same host natively when private database access is configured (see [runtime consolidation](docs/RUNTIME.md)). SOAP credentials stay on the server; credentials in query strings are disabled. Display defaults are 1080p/high quality with device-pixel-ratio-aware pointer mapping.

## Native desktop client (Rust)

```sh
python3 scripts/setup-sources.py benilla
cd client/benilla-src
cargo build --locked --profile play -p benilla
cd ../..
WOW_DATA=/absolute/path/to/WoW_3.3.5a/Data bash client/benilla.sh
```

macOS needs Xcode Command Line Tools. Linux also needs ALSA/udev development packages (`libasound2-dev libudev-dev pkg-config` on Ubuntu). Native Windows requires the Rust MSVC toolchain and Visual Studio build tools; run `cargo play` inside the restored source with `WOW_DATA` set in PowerShell. The shell launchers target Linux/macOS. The native desktop path uses ordinary game login and the spectator addon; the browser host owns the custom guest lobby. Native client settings stay under ignored `artifacts/desktop` by default. Optional `WOW_HOST`, `WOW_USER`, `WOW_PASS` and `WOW_CHAR` environment variables configure a server or unattended login; never commit them.

## Smaller PvP asset pack

You can build a standalone MPQ retaining PvP maps and shared gameplay assets while excluding unrelated map terrain. An optional dependency-aware profile also trims unreferenced scenery and environmental audio while preserving dynamic character, gear, pet and spell families. See [PvP asset packing and isolated validation](docs/PVP-ASSETS.md). Original game data stays private and unchanged; the pack is generated locally.

## PvP-only server profile

An isolated server profile trims world data and collision files, disables unused world systems, and protects the trimmed database from automatic upstream updates. See [build, validation and rollback instructions](docs/PVP-SERVER.md). The full installation remains available alongside it.

## Deployment and development

See [deployment](docs/DEPLOYMENT.md), [architecture and branch workflow](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md) and [agent instructions](AGENTS.md). See the [lobby implementation](controller/lobby/README.md) and [optional Fly deployment](deploy/fly/README.md).

Licensing is component-specific: new integration code is MIT; client-derived changes retain MIT/Apache-2.0 terms; TrinityCore/NPCBots-derived changes retain GPL terms. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY.md). Game assets and trademarks belong to their respective owners and are not covered by these source-code licenses.

## Bot development and checks

The controllers use private SOAP; set `ARENA_SOAP_USER` and `ARENA_SOAP_PASS` from your local .env before running them outside Docker.

```sh
python3 controller/arena_ctl.py start 3 random
python3 controller/benchmark.py --smoke --out artifacts/benchmarks/smoke
python3 controller/benchmark.py --quick --out artifacts/benchmarks/baseline
python3 controller/analyze_benchmark.py --help
python3 -m venv artifacts/test-venv
artifacts/test-venv/bin/pip install -r controller/lobby/requirements.txt
artifacts/test-venv/bin/python -m unittest discover -s controller/lobby -p 'test_*.py'
python3 -m unittest discover -s controller -p 'test_*.py'
npm ci
npm run test:recovery
```

Browser checks use installed Chrome; live lobby/input checks require a running GPU-capable client/server and dedicated test guests. Benchmarks create real headless matches and write ignored result artifacts. Use a development server and coordinate with active players. `controller/tune.py` manages experiments, and `docker/conf/arenabrain.params` holds current tuning defaults. See the roadmap before claiming improvements.
