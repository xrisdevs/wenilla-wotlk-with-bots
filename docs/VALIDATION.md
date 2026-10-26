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
