# Third-party attribution

- [Benilla-WotLK](https://github.com/Onixaz/benilla-wotlk), based on [Benilla](https://github.com/samwhosung/benilla): Rust client, MIT OR Apache-2.0. Copyright notices are retained in the source tree and `licenses/BENILLA-*`.
- [Wenilla](https://github.com/Arnesen/wenilla): MIT OR Apache-2.0; browser platform, WASM/Lua support, asset/network gateway and bridge work incorporated into the client patch. Retain upstream notices and dependency licenses in restored source.
- [TrinityCore with NPCBots](https://github.com/trickerer/TrinityCore-3.3.5-with-NPCBots) and [Trinity-Bots](https://github.com/trickerer/Trinity-Bots): server and NPCBot implementation. TrinityCore-derived patches and BotArena core integration are GPL-2.0-or-later, subject to each source file's notices; see `licenses/TRINITYCORE-GPL-2.0.txt`.
- [StormLib](https://github.com/ladislav-zezula/StormLib): MIT; the optional PvP pack builder links against a locally installed library to write MPQ archives. Retain its upstream license when distributing the linked tool.
- Vendored Lua, mlua, Rust crates and other dependencies keep their own licenses. The source patch includes their existing manifests and notices. Consult the restored source when redistributing binaries.

The top-level MIT license does not relicense these components. Blizzard assets, world database contents, names and trademarks are not licensed by this repository. No game assets are included.
