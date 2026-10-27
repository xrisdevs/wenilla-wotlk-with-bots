# PvP addon bundle

Browser builds and `client/benilla.sh` install the same checksum-pinned addon bundle. The installer downloads upstream archives into ignored `artifacts/pvp-addons`, retains bundled notices, applies documented compatibility edits to installed copies, and writes the browser addon index. Third-party source is not vendored into this repository.

| Addon | Version | Current experimental client |
| --- | --- | --- |
| InterruptBar | 1.15, with Wind Shear added | Enabled: enemy interrupt/CC cooldown timers; active icons only, locked, scale 1.1 below centre |
| LoseControl | 3.33 | Enabled: 52 px player CC indicator, roots included; target/focus/party indicators retained |
| OmniCC | 3.0.4 | Enabled: 20 px numeric cooldowns, GCD-sized timers excluded; no duplicate InterruptBar text |
| Quartz | 3.0.3.1 | Enabled: player, target and focus cast bars, with latency; unrelated buff/swing/flight/pet bars and unsupported GCD/range modules disabled |
| Gladius Enhanced | v1.2.2 | Installed, **not enabled**: the client lacks `UnitGUID` and `arena1`–`arena5` opponent feeds |
| SoundAlerter | pinned 3.3.5 archive | Installed, **not enabled**: required unit APIs are missing; audio alerts have not been validated |

Gladius's trinket/DR/enemy frames and SoundAlerter's audio alerts are not usable yet. Installing a compatible original-WoW addon does not supply missing Rust-client APIs. Do not enable them and interpret blank frames as working tracking. The client also currently fails to read external LoadOnDemand addon files, so the bundled OmniCC options panel is not supported. The enabled core uses automatic defaults instead.

The [manifest](../addons/pvp-addons.json) records exact origins, revisions/file IDs and SHA-256 values. Sources: [Gladius](https://github.com/Cortes-Jeremy/Gladius), the [3.3.5 addon archive](https://github.com/NoM0Re/WoW-3.3.5a-Addons), and [Tuller's original OmniCC 3.0.4 release](https://www.curseforge.com/wow/addons/omni-cc/files/454434). Avoid retail or Wrath Classic releases: they target different APIs.

## Settings and installation

Defaults are applied once per account for shared settings and once per character for character-specific settings. Subsequent player changes are retained. Browser saved variables live in that browser profile's local storage; desktop saved variables live under `BENILLA_HOME`. Separate browser profiles/devices have independent preferences.

- `/pvpaddons` reports which addons are loaded and which are waiting for engine support.
- `/ib lock` toggles dragging the interrupt bar; `/ib scale 1.2` changes its scale; `/ib test` previews its timers.
- InterruptBar estimates cooldowns from observed enemy casts. It shares one timer per spell name, so it cannot distinguish two enemy players using the same interrupt. It does not account for every talent/glyph cooldown reduction.
- Spectator mode hides the game UI, including these player-oriented frames. No automatic chat announcements are enabled.

To stage without rebuilding WASM:

```sh
python3 client/install-addons.py artifacts/desktop/AddOns
python3 client/install-addons.py client/benilla-src/web/addons
```

A browser deployment must also copy that complete `addons` directory into its served `/www/addons`. Standard `client/browser.sh build` and Docker builds do this automatically. Updating files does not reload an already-running game VM: return to the lobby and reload the browser.

## Compatibility work and validation

`ArenaCompat` adds Lua post-hooks and login tracking only where the engine lacks them; it does not fabricate units, GUIDs, spell casts or combat events. This experimental engine has no secure/taint execution model. `ArenaPvP` waits for real spell data before configuring profiles. The installer defers InterruptBar construction until spell names exist, fixes Gladius library ordering/case, escapes multibyte Lua string literals for older parser builds, adapts optional Quartz texture methods, disables unused Quartz modules before initialization, and guards LoseControl aura events received before frame initialization. Optional Quartz channel tick tables cannot resolve spell names during initial loading, so channel tick counts are not guaranteed.

Run:

```sh
python3 -m unittest discover -s client -p 'test_install_addons.py'
BROWSER_URL=http://localhost:8096 node client/check-pvp-addons.cjs
```

The rendered check creates a dedicated guest, enters a bot arena, exercises InterruptBar's test timers and OmniCC's real rendering path, casts Holy Light to check Quartz, checks addon errors, and verifies saved preferences across matches. Test timers are synthetic previews, not evidence that an enemy used an interrupt. Live enemy cooldown/CC accuracy requires observing actual combat; do not infer it from `IsAddOnLoaded` alone. Stock FrameXML still has unrelated missing-API errors.
