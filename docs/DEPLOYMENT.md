# Docker deployment

The README's Compose stack can run on a Linux host as well as a desktop. Build on a host with enough RAM; persistent runtime and build data occupy separate volumes. A small development server is possible, but concurrent bot matches and compilation need measurement before selecting hardware.

1. Clone this branch and follow the Docker setup, including your own game data; the TDB setup service fetches the pinned world seed. Keep `.env` mode 0600 and backups private.
2. Keep default loopback bindings. For remote browser testing, forward port 8090 over SSH (`ssh -L 8090:127.0.0.1:8090 USER@HOST`) and visit localhost. This preserves the browser secure-context exception.
3. For a multi-user site, use the **arena-with-bots** branch's guest-session service behind an HTTPS reverse proxy. Do not publish the raw main-branch gateway: its asset routes intentionally have no authentication. The arena branch includes an all-in-one Docker image and Fly example; deploying it is optional and incurs provider charges.
4. Keep MySQL and SOAP private. For remote native play, explicitly configure realm addresses and firewall the game TCP ports for intended users. Never publish DB credentials or reuse a player account as an operator.
5. Back up the database and any arena guest-state database together. Test restoration before upgrades. Keep game assets outside the image/repository. Only distribute or serve assets where you have the necessary rights.

`docker compose logs -f authserver worldserver` shows initialization errors. Failed TDB downloads/checksums, missing maps, incorrect Data paths, insufficient memory and incompatible database revisions are the first things to check. No cloud account, hostname, machine ID or credentials from the original development deployment are included here.
