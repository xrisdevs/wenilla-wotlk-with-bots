# Building a smaller PvP MPQ

The arena branch can create one **standalone MPQ** from your existing English 3.3.5a installation. The gateway accepts a single archive. This branch also fixes version-2 MPQ offsets above 4 GiB in the shared native reader; use a gateway/browser image rebuilt from this revision. No original-archive fallback is needed. This changes client asset storage, not server world loading, server database contents, or memory limits.

The initial profile is deliberately conservative: it removes unrelated high-detail map terrain and retains **all shared models, textures, item appearances, character customization, spells, pets, UI, sound and music**. It is not a minimal dependency-pruned asset set. Further trimming shared assets needs broader gameplay coverage and dependency analysis; this pack does not claim that every retained file is used by PvP.

All maps marked arena or battleground in `Map.dbc` are included. Asset inclusion does not enable a map in the matchmaking roster: Dalaran remains excluded there. Death Knight starting terrain and bounded terrain around the four starting locations used by lobby presets are retained. Other continent terrain, dungeons and raids are excluded. The retained starting zones are staging areas, not supported free-roaming continents. Existing characters parked elsewhere need relocation before using this pack. Server maps/vmaps/mmaps and DBC extraction still use the full installation.

## Build locally

Requirements: restored client sources, Rust/Cargo 1.89 or newer, a C linker, and StormLib. On macOS install StormLib with `brew install stormlib`; on Debian/Ubuntu use `libstorm-dev`. For another installation prefix, set `STORMLIB_DIR` to its prefix (containing `lib/`).

```sh
python3 scripts/setup-sources.py benilla
bash scripts/build-pvp-pack.sh /absolute/path/to/Data artifacts/pvp-pack/release-1
```

Choose a **new output directory** each time. The tool never modifies the originals, overwrites an existing pack, or uploads game data. Files stream from the original archives into the new archive without extracting a second loose-file installation.

The tool uses the actual client's `Chain` resolver, including archive priority and delete markers, to read each winning file. StormLib writes a compressed version-2 MPQ supporting archives above 4 GB. Before publishing `pvp.MPQ`, every included file is reopened with the client reader and checked against its original SHA-256 and length. Interrupted builds remain `.partial` and must not be mounted. `manifest.json` records file hashes, sizes and selection counts; `profile.json` records staging bounds. All generated outputs belong under ignored `artifacts/`, never in Git.

Archive enumeration uses the source MPQs' internal listfiles. Installations with incomplete listfiles can hide files from enumeration: full-file round-trip checks do not prove completeness. Validate real gameplay and asset requests before adopting a pack. The checked-in profile is for the current arena preset races and normal spawn coordinates; change it when staging locations change.

## Test without fallback

Run a temporary browser service on a separate local port against the existing development server:

```sh
export PVP_MPQ="$PWD/artifacts/pvp-pack/release-1/pvp.MPQ"
docker compose -f docker-compose.yml -f docker/pvp-pack.compose.yml \
  --profile browser run -d --no-deps --name wenilla-pvp-check \
  -p 127.0.0.1:8095:8090 -e ARENA_PUBLIC_ORIGIN=http://localhost:8095 browser

BROWSER_URL=http://localhost:8095 TEST_WIDTH=1920 TEST_HEIGHT=1080 TEST_ARENA=na TEST_COMBAT_SECONDS=75 \
  ASSET_REPORT="$PWD/artifacts/pvp-pack/reduced-requests.json" node client/check-lobby.cjs
```

The overlay replaces `/game-data` with the single MPQ file. Older gateway images cannot read offsets above 4 GiB: rebuild with `docker compose --profile browser build browser` before testing. During development, a newly compiled Linux gateway can instead be bind-mounted over `/usr/local/bin/wenilla-host` in the temporary container; the WASM files need no change for this reader fix. Inspect mounts to verify the full directory is absent. Keep the usual full-data browser on 8090 for comparison. The tests create dedicated guest characters and matches; do not run against someone else's active game session.

Capture a full-data baseline by running the same test with `BROWSER_URL=http://localhost:8090` and a different report filename. Check all its successfully fetched assets were included:

```sh
python3 scripts/check-pvp-requests.py artifacts/pvp-pack/release-1/manifest.json \
  artifacts/pvp-pack/full-requests.json
```

Repeat with `TEST_ARENA=be` and `rl`, different preset classes, and battleground sessions. A passing lobby/arena test does not establish full battleground coverage. Existing optional asset 404s should be compared against the original installation, not automatically blamed on the pack.

Remove only the temporary test container when finished:

```sh
docker rm -f wenilla-pvp-check
```

## Adopt and roll back

After verification, the same overlay can start the regular browser service with the pack:

```sh
docker compose -f docker-compose.yml -f docker/pvp-pack.compose.yml \
  --profile browser up -d --no-build browser
```

This recreates the browser service and interrupts its active connections. Do it between sessions. Return to the full data mount with the original `docker compose --profile browser up -d --no-build browser` command. Keep the originals for rollback and server extraction. Cloud rollout is separate; building or testing a local pack never redeploys the live server.

## Initial validation results

The initial English 3.3.5a pack contains 194,054 files and excludes 5,222 listed files. The resolved source archive chain was 17.07 GB (15.90 GiB); the standalone MPQ is 10.24 GB (9.54 GiB), a **40.0% reduction**. Sizes vary with the supplied installation. Every packed file passed SHA-256 and length verification through the updated client reader.

The 1920×1080 browser test passed hero/gear/talent inspection, spectating, bot participation, human queue cancellation and returning to the lobby with the single MPQ mounted. The completed reduced run loaded Lordaeron and Nagrand; its 3,161 distinct successfully requested asset paths were all present, with the same seven optional missing paths as the original installation. All 2,836 successful baseline paths were also present. An excluded Northrend WDT correctly returned 404 while an included arena WDT returned 200 from the isolated gateway.

A separate extended Blade’s Edge observation run disconnected/recovered with **both the reduced pack and the original full MPQs**. That runtime issue remains unresolved; archive integrity checks and the shorter completed gameplay test do not establish long-session stability. Battleground assets are included and byte-verified, but full battleground gameplay has not yet been validated. The pack has not been rolled out to cloud hosting.
