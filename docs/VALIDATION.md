# Publication validation

Checks performed while preparing this repository:

- Browser patch applies to the pinned Benilla-WotLK revision.
- Rust gateway: 12 unit/integration tests passed, including data serving, static assets and WebSocket forwarding.
- Browser JavaScript: 7 tests passed.
- Docker Compose configuration and Dockerfile build checks passed.
- Python syntax and shell syntax checks passed.
- Fresh Git history scanned with Gitleaks; no leaks found. Tracked files also reviewed for private paths, deployment identifiers, database state and game assets.

The migration did not repeat a complete clean C++ server and WASM compilation or deploy a new cloud instance. The source patches originated in the working development stack; new packaging should still be exercised on the intended deployment host. A Dockerfile build check validates its instructions, not a full image build.

Arena branch checks additionally passed:

- Server patch applies to its pinned NPCBots revision; custom patch script reports all 44 edits already present after patch restoration.
- Fresh arena client restoration and browser staging, including an idempotent second setup pass.
- 19 lobby service tests and 13 tuner tests.
- Chrome crash-recovery regression: failed WASM iframe removed, health outage awaited, guest cleanup performed once, fresh lobby loaded.
- npm dependency audit: no reported vulnerabilities in the locked test dependency set at publication time.

Live matchmaking, graphical tooltips and headless arena benchmarks were not rerun against a newly built migration stack. No private prior-session logs or result databases are distributed.

## Local Docker migration verification

The arena branch was subsequently built and exercised as the full local Compose stack:

- Server image and incremental C++ build/install passed against matching pinned source.
- Linux ARM64 browser image built WASM, optimized it and compiled the Rust gateway. The 8 GB Docker VM needed the game services stopped plus temporary swap during WASM packaging. The temporary swap was removed afterward.
- Database and guest state were restored into independent volumes and existing account/character counts checked before test guests were added.
- Authenticated database readiness and worldserver's in-process TDB cache verification passed; no separate setup container is needed.
- 21 lobby service tests, 13 tuner tests and the Chrome recovery test passed.
- The rendered Docker-hosted client passed hero selection/rotation, graphical gear/talent/glyph inspection, spectator entry/return, bot participation, player queue cancellation and selecting a second hero without reloading.
- The local health endpoint reports ready with browser, authserver, worldserver and database containers running.

Live testing exposed a generated-name triple-letter rejection; name generation and typed-name validation now cover that game-server constraint. The changes are part of this branch, not a private local override.
