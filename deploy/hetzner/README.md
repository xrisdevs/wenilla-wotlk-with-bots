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

Follow the root README to build/install the server, extract server data and initialize the database. Supply your own game assets under `$WOW_CLIENT_DIR/Data`, readable by container UID/GID 65534 (for example root:65534 ownership, directories 0750 and files 0640); serving them requires the appropriate rights. The root startup automatically downloads/verifies TDB, applies core updates, and `scripts/init-arena.py` adds arena presets and a private operator.

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

## Local-only push-to-deploy pipeline

`pipeline.py` is a one-shot local worker that polls the remote `arena-with-bots` ref. Schedule it every 60 seconds with `install-watcher.py` on macOS (or a user systemd/cron timer on Linux). This runs on your own machine, not GitHub Actions. The machine must be awake, online, able to use its SSH key without an interactive prompt, and Docker must be running. Only pushes to the named branch trigger deployment; uncommitted local work is never deployed.

Store configuration under ignored `artifacts/hetzner/pipeline.json`:

```json
{
  "repository": "https://github.com/xrisdevs/wenilla-wotlk-with-bots.git",
  "state_directory": "/private/absolute/path/to/pipeline-state",
  "ssh_config": "/private/absolute/path/to/ssh-config",
  "ssh_host": "wenilla-hetzner",
  "remote_directory": "/opt/wenilla",
  "url": "https://arena.example.com"
}
```

After verifying the first deployment, create `state.json` in that private state directory with `{"deployed":"FULL_VERIFIED_COMMIT_SHA"}`. Then:

```sh
python3 deploy/hetzner/pipeline.py --config artifacts/hetzner/pipeline.json --check
python3 deploy/hetzner/install-watcher.py --config artifacts/hetzner/pipeline.json
```

The worker locks out overlapping runs, clones isolated releases, runs publication/Python checks and browser recovery checks when applicable, rebuilds changed server/client components, transfers architecture-matched images, briefly pauses the browser service for matching private SQL/guest-state backups, activates the revision and checks the public health endpoint. A newer push arriving during a build supersedes that build. Asset files and initial seeds are not uploaded again. The C++ build uses separate `wenilla-release` volumes, leaving your local running server's install untouched.

On a Docker VM with less than 12 GB RAM, browser builds temporarily add 8 GB of swap inside the Docker Linux VM using a privileged helper container; the worker removes it afterward. Keep at least 12 GB host disk space free for this. Build caches persist for subsequent releases.

Failures are recorded and that commit is not retried endlessly. Inspect the local `pipeline.log` and remote `artifacts/deploy/<sha>/` backups, then invoke the worker with `--retry`, or push a corrected commit. Database migrations are not automatically rolled back. Source/install backups and SQL backups are retained privately; review retention and free disk space regularly. Keep a separate off-machine backup for disaster recovery.

To disable the macOS watcher: `launchctl bootout gui/$(id -u)/dev.wenilla.hetzner-deploy`. Logs and configuration remain local. The helper transfers only application code/images/binaries; database and operator secrets stay in the remote ignored `.env`.
