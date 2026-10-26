# Docker deployment

The README's Compose stack can run on a Linux host as well as a desktop. Build on a host with enough RAM; persistent runtime and build data occupy separate volumes. A small development server is possible, but concurrent bot matches and compilation need measurement before selecting hardware.

1. Clone this branch and follow the Docker setup, including your own game data; worldserver startup fetches the pinned world seed. Keep `.env` mode 0600 and backups private.
2. Keep default loopback bindings. For remote browser testing, forward port 8090 over SSH (`ssh -L 8090:127.0.0.1:8090 USER@HOST`) and visit localhost. This preserves the browser secure-context exception.
3. For a multi-user site, use the **arena-with-bots** branch's guest-session service behind an HTTPS reverse proxy. Do not publish the raw main-branch gateway: its asset routes intentionally have no authentication. The arena branch includes an all-in-one Docker image and Fly example; deploying it is optional and incurs provider charges.
4. Keep MySQL and SOAP private. For remote native play, explicitly configure realm addresses and firewall the game TCP ports for intended users. Never publish DB credentials or reuse a player account as an operator.
5. Back up the database and any arena guest-state database together. Test restoration before upgrades. Keep game assets outside the image/repository. Only distribute or serve assets where you have the necessary rights.

`docker compose logs -f authserver worldserver` shows initialization errors. Failed TDB downloads/checksums, missing maps, incorrect Data paths, insufficient memory and incompatible database revisions are the first things to check. No cloud account, hostname, machine ID or credentials from the original development deployment are included here.

## Arena all-in-one image on a generic Docker host

The Compose browser service above builds the WASM client in Docker. For a single persistent deployment container, the same runtime used by the Fly template can run on any compatible Linux Docker host:

1. Complete local setup and build the WASM client (`bash client/browser.sh setup` then `build`, or copy `/www` out of the Compose browser image into `client/benilla-src/web/dist`).
2. Run `python3 deploy/fly/prepare.py` against your initialized development database. It stages browser files and SQL under ignored `artifacts/fly`. Auth/character seeds include only schema and reference tables, never player rows; world seeds contain world content. Keep all seeds private.
3. Build `docker build -f deploy/fly/Dockerfile -t wenilla-arena .`.
4. Prepare a private persistent directory containing `game-data/` (your Data contents) and `server-data/` (extracted dbc/maps/vmaps/mmaps). Verify both, then create `.ready` in each.
5. Create a private `runtime.env` **outside the repository** with generated `ARENA_DB_PASSWORD`, `ARENA_SOAP_PASS` (32+ alphanumeric characters), and `ARENA_PUBLIC_ORIGIN=https://YOUR-HOST`. Do not reuse your development secrets.
6. Run `docker run -d --name wenilla-arena --restart unless-stopped --env-file /private/path/runtime.env -v /private/path/persist:/persist -p 127.0.0.1:8090:8090 wenilla-arena`, and proxy HTTPS to 8090 using your chosen reverse proxy. For localhost testing set the public origin to `http://localhost:8090`.

Only 8090 is published; database, SOAP, login/world TCP and the raw gateway stay inside the container. MySQL, guest identity and game data persist under `/persist`. Back this directory up consistently. `/healthz` checks listeners and database access. Queues are in memory and do not survive restart. This is one machine, not a horizontally scalable service.
