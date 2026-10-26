# Hetzner / standalone Linux Docker host

This deploys the same `arena-with-bots` Compose stack behind Caddy HTTPS. No Fly account is required. The hostname, IP, credentials, private keys and game assets belong in private deployment state, never in Git.

## Provision and prepare

Use a compatible Linux host with at least 4 CPU cores, 8 GB RAM and enough disk for your assets, databases and images. ARM64 CAX servers can run images built on an Apple Silicon Docker host; x86 servers need amd64 images. Compile the large WASM client elsewhere when running on a small VM. Check live availability and pricing before provisioning; cloud servers incur charges until deleted.

Restrict SSH to administrator addresses and allow inbound TCP 80/443. Install Docker and Compose v2. Clone this repo at `/opt/wenilla`, select `arena-with-bots`, and restore its pinned server source. Set up private `.env` using `scripts/init-env.py`, then configure:

```text
WOW_CLIENT_DIR=/srv/wenilla/game-client
PUBLIC_HOSTNAME=arena.example.com
ARENA_PUBLIC_ORIGIN=https://arena.example.com
```

Point the hostname's DNS to the host. For temporary testing an IP-based DNS service can be used, but a domain you control is preferable for a stable address. Caddy obtains and renews a public TLS certificate automatically. WebGPU requires HTTPS for remote access.

Follow the root README to build/install the server, extract server data and initialize the database. Supply your own game assets under `$WOW_CLIENT_DIR/Data`; serving them requires the appropriate rights. The root startup automatically downloads/verifies TDB, applies core updates, and `scripts/init-arena.py` adds arena presets and a private operator.

Alternatively, transfer **architecture-matched** prebuilt `wenilla/trinitycore` and `wenilla-wotlk-browser` images via `docker save | ssh ... docker load`, along with installed server binaries and extracted data into the matching Compose volumes. Copy only clean database seeds if using pre-initialized world data; never copy development player accounts or browser cookies. Keep seed dumps outside Git. The server's installed binaries must match the pinned/patched source and database revision.

## Start and operate

Run from the repository root:

```sh
docker compose -f docker-compose.yml -f deploy/hetzner/compose.yml --profile browser up -d --no-build db authserver worldserver browser caddy
curl -f https://arena.example.com/healthz
```

Only Caddy is internet-facing. MySQL stays on the Docker network; SOAP/game TCP ports and the browser HTTP port remain loopback-only. The raw gateway stays private inside the browser container. The lobby enforces guest ownership and the configured public origin.

Back up MySQL and the lobby guest-state volume consistently, plus Caddy certificate storage. Persistent Docker volumes survive container replacement but do not survive deleting the cloud machine's disk. Provider backups/snapshots have additional charges; enable them deliberately. This is a single-host deployment with in-memory queues, not a multi-node cluster.

Use the same two Compose files for status, logs, updates and shutdown. Never run `down -v` unless intentionally deleting persistent state. Keep the previous deployment intact until the new endpoint passes a rendered lobby/arena test.
