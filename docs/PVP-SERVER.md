# Isolated PvP server profile

This is an opt-in **English arena/battleground server**, built alongside the full installation. It is still TrinityCore with MySQL. The original source databases, assets and containers are not pruned or replaced. Do not run this overlay under the full installation's Compose project name.

## What changes

- Copies auth, characters and world into a new, empty project's database. Takes a compressed private backup and a consistent SQLite guest-ownership backup first. The guest mappings are copied and checked against the cloned accounts. Preserves player/account data, all item and creature/gameobject templates, gear presets, spells, quests, trainers, pets, loot and scripts used by shared gameplay.
- Removes non-PvP creature/gameobject spawns (retaining NPCBot template spawns), unused spawn references, continent wandering-bot nodes, non-English locale rows, quest map POIs, weather and unreferenced waypoint paths. Shared definitions are deliberately conservative: this is not a minimal dependency closure of every template or script.
- Retains all eleven supported 3.3.5a arena/battleground maps, Death Knight staging, and bounded starting-area terrain. Preserves all DBCs and dynamic gameobject collision models, plus every collision model referenced by retained terrain. This keeps battleground gates, ships and vehicles available. Generates navigation for the six battlegrounds as well as keeping the five existing arena navmeshes.
- `PvpOnly.Enabled` skips localization, weather and quest-POI loading, outdoor-PvP/battlefield initialization and updates, auction-bot initialization/updates, and continent transport spawning. Battleground managers, arena seasons, holiday events and transport templates remain enabled.
- Rejects entry into unsupported maps. Maps 0, 1, 530 and 609 remain staging exceptions; their presence does not make this an open-world realm. Existing copied characters outside supported areas need relocation on the clone before use. No character positions are silently rewritten.
- Disables continent wandering maps **as well as their population count**. NPCBots otherwise requires spawn nodes even with a zero population.

## Build a fresh profile

Use Docker Compose with `!override` support (2.24.4+). Start from a healthy initialized full stack and restored sources. Commands below use `wenilla-wotlk` as the full project and `wenilla-pvp-server` as a **new** target. Use a new target name for subsequent generations. Never replace a populated target with these commands.

```sh
python3 scripts/setup-sources.py all
bash scripts/apply-custom.sh

# Compile into the target's separate install/build volumes.
docker compose -p wenilla-pvp-server -f docker-compose.yml \
  -f docker/pvp-server.compose.yml --profile build run --rm build

# Create a private backup, import into the empty target, trim, verify critical counts.
python3 scripts/prepare-pvp-server.py --source-project wenilla-wotlk \
  --project wenilla-pvp-server --output artifacts/pvp-server/generation-1

# Source is read-only; destination must be empty.
docker run --rm \
  -v wenilla-wotlk_tc-data:/input:ro -v wenilla-pvp-server_tc-data:/output \
  -v "$PWD/scripts/trim-pvp-data.py:/trim.py:ro" \
  -v "$PWD/docker/pvp-server.json:/profile.json:ro" \
  wenilla/trinitycore python3 /trim.py /input /output --profile /profile.json

# Generate missing PvP navigation against the reduced terrain/collision data.
docker run --rm -w /work \
  -v wenilla-pvp-server_tc-install:/opt/trinitycore:ro \
  -v wenilla-pvp-server_tc-data:/work wenilla/trinitycore bash -c \
  'set -e; for m in 30 489 529 559 562 566 572 607 617 618 628; do prefix=$(printf "%03d" "$m"); if ! ls mmaps/${prefix}*.mmtile >/dev/null 2>&1; then /opt/trinitycore/bin/mmaps_generator "$m" --threads 2; fi; done'

docker run --rm -v wenilla-pvp-server_tc-data:/data \
  -v "$PWD/scripts/verify-pvp-data.py:/verify.py:ro" wenilla/trinitycore \
  python3 /verify.py /data --record-navigation

# Build the shared browser image if it is not already built from this revision.
docker compose --profile browser build browser

docker compose -p wenilla-pvp-server -f docker-compose.yml \
  -f docker/pvp-server.compose.yml --profile browser \
  up -d --no-build db authserver worldserver browser
```

The local preview is **http://localhost:8096**. Private SOAP is on localhost:17878; native authentication/game ports are 13724/18085. The browser connects to the isolated services on their internal Docker ports. No cloud deployment is triggered. `PVP_BROWSER_IMAGE` can select a separately built browser image.

For faster incremental server builds, an inactive build cache and install can be **copied** into the new target's empty volumes. Never mount the active full installation's build/install volumes writable into this profile's build job. Reduce `JOBS` if Docker is short of memory.

To combine this with the reduced client MPQ, add `-f docker/pvp-pack.compose.yml` and set `PVP_MPQ` as described in [PvP assets](PVP-ASSETS.md). Use a gateway built with the large-MPQ reader fix.

## Update policy and rollback

`PVP_SERVER_PROFILE=1` forces `Updates.EnableDatabases=0` and `Updates.AutoSetup=0`. Startup requires a completed `world.pvp_profile_metadata` record and a verified data manifest; it also checks the source pin. It does not download TDB or link cached full SQL into the working directory. Its `/tdb` volume stays empty. Keep the full installation's cache for rollback; it is not copied into the PvP deployment.

**Never apply upstream world SQL updates directly to the trimmed world.** Update a separate full baseline, regenerate a fresh profile, validate it, then switch environments. This prevents updates from reintroducing removed spawns and translations. The generation script refuses any target containing auth/world/character tables or an existing guest database, so it cannot overwrite live player state. For a consistent production snapshot, pause new registrations and character changes while taking the SQL and guest-state backups; they are two different stores.

For a later upgrade of a live PvP realm, player persistence needs a coordinated migration from that realm during a maintenance window. The current generator copies its chosen full source and is intended for initial creation/evaluation; do not use an old full baseline to replace newer PvP player progress.

Stop only the isolated project to roll back to the unchanged original browser on 8090. Retain its volumes and private backup until you no longer need them. Do not use `down -v` on the full project.

## Validation and limitations

The first local generation reduced world tables from about **417 MiB to 143 MiB**. Preserved account, character, item, creature/gameobject-template and gear-preset counts matched the full snapshot. Extracted data fell from about **999 MiB to 370 MiB**, including newly generated battleground navigation. The PvP profile has no 325 MiB TDB cache.

Observed startup worldserver RSS was approximately **779 MiB**; the existing full server was using approximately **1.35 GiB after gameplay**. These are different process histories, not a controlled RAM benchmark. Startup logs reported 2 seconds for the trimmed server and 7 seconds for the full server; cache state was not controlled.

The combined reduced-client/reduced-server stack passed the 1920×1080 lobby test: graphical hero/gear/talent inspection, spectating, bot participation, human queue cancellation and return. Nagrand and Lordaeron test matches completed with valid results. Full battleground matches and every class/spec combination have not been exhaustively tested. The earlier long-session disconnect observed with full and reduced client assets remains a separate unresolved issue.

Some retained world-only SmartAI templates report references to removed world spawns during startup. Their templates remain for conservative shared-data compatibility; this profile does not promise those world quests or scripts work. Keep the full baseline available for any functionality outside the PvP scope.

Generated SQL, extracted data, player snapshots, manifests and logs stay in ignored private artifacts/volumes. Only build scripts, profiles and source patches belong in Git.
