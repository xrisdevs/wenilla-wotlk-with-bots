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

## Dependency-aware scenery and audio profile

The optional second profile follows static dependencies instead of retaining every shared scenery file:

```sh
bash scripts/build-pvp-pack.sh /absolute/path/to/Data artifacts/pvp-pack/dependency-release \
  tools/pvp-pack/dependency-profile.json
```

It follows selected terrain into WMO buildings and their numbered groups, M2 models, texture paths, skin/animation sidecars, and ground-cover models whose DBC names need a directory prefix. Zone audio follows retained terrain areas, parent zones, all supported PvP areas, retained WMO name sets, and animation sound events. Sound-related DBCs conservatively add possible sound-kit dependencies. Login music and ghost/underwater ambience remain available. MP3/OGG files are stored without redundant zlib compression; their original bytes are unchanged.

Character customization, every item/creature/spell family, interface, tilesets, minimaps and other runtime-selected textures remain intact. This includes all preset classes, bot appearances, pets, enchants and spell variants; the pack is still deliberately broader than the current presets. It is not a claim of the smallest possible installation. Only scenery and environmental-audio groups are candidates for dependency removal in this pass. No database or DBC rows are rewritten.

Each build writes `dependencies.json`, including a reason for every retained file, selected area/WMO ids, and references unavailable in the original chain. Some original references are optional or obsolete; this report is not itself proof of a missing-file regression. A referenced file that exists in the chain but is absent from its listfiles stops the build. Malformed chunk/DBC bounds and missing WMO group files also stop it.

To inspect the closure without writing an MPQ, compile the tool as above, then use a **new** report directory:

```sh
artifacts/pvp-pack-target/release/wenilla-pvp-pack plan \
  /absolute/path/to/Data tools/pvp-pack/dependency-profile.json artifacts/pvp-pack/plan-1
```

A local profile may add `request_reports`, an array of captured asset-report paths. Successful observed requests add roots; lack of a request never authorizes deleting dynamic assets. Keep profiles containing private paths under `artifacts/`.

After the candidate's complete byte verification, compare it with the previous conservative pack and captured sessions:

```sh
python3 scripts/check-pvp-closure.py \
  artifacts/pvp-pack/release-1/manifest.json \
  artifacts/pvp-pack/dependency-release/manifest.json \
  artifacts/pvp-pack/dependency-release/dependencies.json \
  artifacts/pvp-pack/full-requests.json
```

This rejects lost map roots, changed retained bytes, missing dynamic families, successful baseline requests omitted from the candidate, and candidate 404s for files pruned from the previous pack. Use `TEST_ALL_PRESETS=1` with the rendered lobby test to inspect every preset's model, talent and gear views before the normal arena flow. Repeat the candidate test for `na`, `be` and `rl` and audit their reports too. Preset inspection and byte/dependency checks for battleground maps are distinct from full battleground gameplay coverage.

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

The overlay replaces `/game-data` with the single MPQ file. Older gateway images cannot read offsets above 4 GiB: rebuild with `docker compose --profile browser build browser` before testing. The arena Docker image uses `wenilla-arena-host`, which links the gateway library directly. Rebuild that image for reader changes; the WASM files need no change for a native reader fix. Inspect mounts to verify the full directory is absent. Keep the usual full-data browser on 8090 for comparison. The tests create dedicated guest characters and matches; do not run against someone else's active game session.

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

## Dependency profile measurements

The dependency profile produces 170,889 files in an 8,568,920,871-byte archive (7.98 GiB). This is **16.3% smaller than the previous 9.54 GiB pack**, saving 1.67 GB, and **49.8% smaller than the original archive chain**. Every packed file passed length and SHA-256 verification through the client reader. The closure audit retains all 12 map roots and the complete protected dynamic families, with unchanged bytes for retained files.

At 1920×1080, all ten preset model/gear/talent inspections passed with only the candidate MPQ mounted. Complete spectator, bot-participation, queue-cancellation and return flows passed for Nagrand, Blade’s Edge and Lordaeron. Baseline and candidate request reports produced zero closure errors and the same seven optional missing paths. The first all-presets run lost its browser frame after entering Nagrand, during return to the lobby; a fresh Nagrand run passed the complete flow. That intermittent failure is not diagnosed, and these results do not establish long-session stability or full battleground gameplay coverage.

The candidate was adopted only by the isolated local PvP preview. The original data, previous pack, full development stack and cloud deployment remain unchanged.
