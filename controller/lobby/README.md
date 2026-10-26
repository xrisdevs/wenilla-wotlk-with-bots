# In-game arena lobby

`client/browser.sh serve` runs the game/data gateway on loopback port 8092 and this same-origin lobby on port 8090. On first use it creates an isolated Python environment and installs the pinned requirements. Build/install the updated server with `scripts/apply-custom.sh` and the usual Docker build first.

The browser loads the game first. `client/lobby/hero-lobby.lua` builds the selection screen from native WoW frames, buttons, fonts and the character-preview renderer. The lobby fills the viewport, with no header/footer backplates. Drag the hero horizontally to rotate it. The selected race/class wears the preset’s real equipment display IDs; Equipment shows native item tooltips with stats, enchants, gems and set bonuses. Talents & Glyphs shows all three graphical talent trees, preset ranks, prerequisites and six glyphs. These are read-only preset inspections. `world-lobby.lua` owns match loading, queue status and return controls. The HTML host contains only the game iframe. Returning logs out through an ownership-checked server action and reuses the loaded client.

Each browser receives an opaque HttpOnly, SameSite guest cookie. The server creates a unique ordinary (security level 0) WoW account and retains its credentials in `artifacts/lobby/state/guests.sqlite`, inside a private directory. Do not publish that database. `ARENA_LOBBY_HOME` can relocate persistent state. Removing browser cookies loses access to that guest; this is a guest flow, not an account-recovery system.

The lobby offers ten level-80 starting builds, one per class. The explicit talent allocations, glyphs and action-bar candidates are in `builds.json`. These are starting arena presets, not claims of competitive optimization. Equipment, enchants and gems reuse `botarena_gear` / `botarena_gear_gems` (Wrathful Gladiator, Season 8). The server validates each talent rank, equips through normal item checks, learns class trainer spells and fills major/minor glyph slots. Changing the catalog requires `python3 controller/lobby/generate_header.py`, rebuilding the server, and restarting the lobby.

- **Watch** hides the character selection and offers match size and arena settings (Nagrand, Blade’s Edge, Lordaeron or random), then creates a bot-only match and joins the guest as a spectator.
- **Bots** adds one human to a team filled with bots; the opposing team consists of bots.
- **Players** uses distinct 2v2 and 3v3 queues, requiring exactly four or six online human characters. Healers are distributed between teams. This is unrated FIFO matchmaking, not an MMR ladder. No bot backfill occurs. While waiting, the game shows the selected hero, equipment/talents, player count, elapsed time and Cancel Queue.

Queue polls are heartbeats. After 20 seconds without a heartbeat, membership expires on the next queue update. Cancellation is explicit and server-checked. The server revalidates every player before creating a match. Returning to the lobby leaves the match and releases spectator state. Closing a browser is a disconnect, subject to the game's ordinary disconnect handling.

The browser can request only bounded operations on its own character. It never receives SOAP credentials or GM account access. Guest camera buttons use `.botarena view`, restricted to the caller's viewpoint; provisioning and human-match creation use the console-only `.botarena lobby` operator command. The game/data gateway stays on loopback behind the lobby's guest-cookie boundary. See [Fly deployment](../../deploy/fly/README.md) for the persistent hosted stack.

## Verification

```sh
artifacts/lobby/venv/bin/python -m unittest discover -s controller/lobby -p 'test_*.py'
```

`check_live.py` creates dedicated test guests and validates all ten builds, then creates actual player-only 2v2 and 3v3 matches. It uses a small native protocol peer so ten rendering clients are not needed. Build it with:

```sh
cp controller/lobby/probe.rs client/benilla-src/crates/benilla-protocol/examples/lobby_probe.rs
cd client/benilla-src
RUSTC="$(rustup which rustc)" RUSTDOC="$(rustup which rustdoc)" cargo build -p benilla-protocol --example lobby_probe
cd ../..
artifacts/lobby/venv/bin/python controller/lobby/check_live.py
```

Test identity cookies and logs stay in ignored `artifacts/lobby/`. The live check leaves its own matches and terminates its own peers when finished. It does not use existing player accounts.

`node client/check-lobby.cjs` runs the rendered guest flow, including the race/class mapping, spectator entry, 1080p buffer, return to the lobby and saved-character list. It uses Playwright from `PLAYWRIGHT_MODULE` or the root `npm ci` installation.

Spectator entry stays covered until the server attaches the first team viewpoint after teleport. It hides the ordinary character UI and keeps the arena HUD; camera switching remains manual.

`python3 controller/lobby/check_spawns.py` checks all 18 bots across the three enabled arenas through the full preparation countdown and verifies the gates open. It stops only its own matches.

Graphical catalog metadata comes from local WotLK DBCs: run `python3 controller/lobby/generate_ui_catalog.py` after changing presets. The lobby adapts its rendering resolution to the browser aspect ratio (at least 1080 pixels high); arenas use 1920×1080. Real device pixel ratio is retained for pointer alignment.

The selection screen uses the native `GameTooltip` widget with level-80 tooltip lines captured from the same client and server-provisioned presets. In-world inspection calls `SetInventoryItem`, `SetTalent` and `SetGlyph` directly, with a short hover refresh for late-arriving data. Regenerate the pre-login snapshot after loadout or tooltip-renderer changes with `node controller/lobby/generate_tooltips.cjs`; `GEAR_ONLY=1` refreshes equipment while preserving the talent/glyph capture. The generator uses dedicated guest characters and intercepts its own play/queue requests, so it never joins a real matchmaking queue. It logs each class and refuses incomplete tooltip captures.

Arena entry switches to the stock selection screen, selects the requested roster entry, and enters on separate updates. A stale roster is re-requested before creating anything. Preparation checks the connected character name, limits transient retries to 45 seconds, and displays failures with Return to Lobby. Display resizing uses a fixed target instead of feeding canvas size changes back into CSS, with bounded retry for stale high-DPI resize events.

The outer host recovers from uncaught client errors, lost graphics devices, disconnected sessions and stalled frame updates by discarding the game iframe. It waits for server readiness, cancels this guest's queue and logs out only this account's online characters, then starts a fresh client at the custom lobby without automatically joining another match. Repeated failures use a bounded backoff; hidden tabs are exempt from the frame watchdog. This cannot recover a browser process that the operating system has killed. Run `node client/check-recovery.cjs` for the crash/server-unavailable regression test.
