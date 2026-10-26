# Reproducible world database setup

`docker/tdb.json` pins the official **TDB335.26091** release used by this project, its download URL, and SHA-256 checksums of the compressed archive and extracted SQL. The large database is not stored in Git.

After building the server image, `docker compose up -d db authserver worldserver` starts a one-shot `tdb` service automatically. It downloads the archive from TrinityCore, verifies it, extracts only the expected SQL file, verifies that too, and atomically publishes the file in `tdb-cache`. Interrupted downloads cannot become a valid cached SQL file. An existing cached SQL file is verified before reuse, allowing offline restarts once populated.

Worldserver waits for successful setup, then uses TrinityCore's normal database initializer/updater. This download step never connects to MySQL and never drops or replaces a populated database. Preserve existing database volumes during upgrades; changing the pin does not automatically reset them.

To fetch explicitly: `docker compose run --rm tdb`. To diagnose failure: `docker compose logs tdb`. A checksum mismatch stops startup; inspect/remove only the corrupt cache file, never the database volume. The archive is roughly 45 MiB and the SQL roughly 279 MiB. Game assets still come from your own 3.3.5a Data directory.

On `arena-with-bots`, run `python3 scripts/init-arena.py` after the first successful world import, then restart worldserver. This adds our operator and Season 8 gear presets; the upstream NPCBots updater supplies bot tables. Everyone starts from the same pinned world seed plus this branch's customizations, without copying private accounts or characters.

For non-Docker use, install Python 3 and `7z`, then run:

```sh
python3 docker/scripts/fetch-tdb.py --manifest docker/tdb.json --directory tdb
```

The optional arena all-in-one/Fly deployment still stages its clean world seed from the initialized development database, so it includes NPCBots updates and arena presets. See that deployment's README; it must not import the raw TDB over a live world.

Upstream: https://github.com/TrinityCore/TrinityCore/releases/tag/TDB335.26091 . Keep attribution and applicable upstream terms when redistributing database content. This repository automates retrieval from the official release; it does not bundle Blizzard client assets.
