# Publication validation

Checks performed while preparing this repository:

- Browser patch applies to the pinned Benilla-WotLK revision.
- Rust gateway: 12 unit/integration tests passed, including data serving, static assets and WebSocket forwarding.
- Browser JavaScript: 7 tests passed.
- Docker Compose configuration and Dockerfile build checks passed.
- Python syntax and shell syntax checks passed.
- Fresh Git history scanned with Gitleaks; no leaks found. Tracked files also reviewed for private paths, deployment identifiers, database state and game assets.

The migration did not repeat a complete clean C++ server and WASM compilation or deploy a new cloud instance. The source patches originated in the working development stack; new packaging should still be exercised on the intended deployment host. A Dockerfile build check validates its instructions, not a full image build.
