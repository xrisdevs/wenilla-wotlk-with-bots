# Proposal: a distributable Rust host with an embedded Trinity engine

Status: source-backed feasibility research, **not implemented**. The working runtime remains the Rust arena host, TrinityCore auth/world services and MySQL. Paths below refer to the restored, pinned `server/` source tree.

## Recommended direction

Keep TrinityCore/NPCBots combat in C++, link it behind a small C ABI, and let Rust own orchestration. Prefer one executable with a separate engine-worker mode before attempting one process for everything. The same executable can launch a worker that invokes the linked engine library; a native crash can then restart that worker and return the browser to the custom lobby without killing the host.

Keep MySQL during that first prototype. Separately move static world data into versioned local packages, then evaluate SQLite for mutable state. These changes target deployment complexity, startup and memory overhead. Neither inherently improves combat simulation throughput.

## Existing integration points

The CMake targets in `src/server/{game,shared,database,scripts}/CMakeLists.txt` already build linkable libraries. `src/server/worldserver/CMakeLists.txt` links those into the executable. `src/server/worldserver/Main.cpp` owns configuration, logging, Asio, DB pools, scripts, sockets, workers, the world update loop and shutdown. Extract that lifecycle into a reusable library while keeping the existing worldserver entrypoint working.

`World::QueueCliCommand` in `src/server/game/World/World.h` and `World.cpp` provides a control boundary processed on the world thread. `TCSoap/TCSoap.cpp::ns1__executeCommand` already enqueues commands there and waits for completion. The Rust host's `runtime/arena-host/src/backend.rs::Soap::command` is the current transport seam. `custom/scripts/BotArena/botarena.cpp` already exposes build preparation, matches, spectating, leaving and JSON status.

A first versioned C ABI should expose lifecycle, allowlisted request submission, response polling, stop requests and owned-buffer disposal. Copy request bytes into engine-owned memory and return owned snapshots. Do not expose `Player*`, `Map*`, STL types or borrowed strings to HTTP tasks. World mutation stays on the engine thread. A canceled Rust future must not free callback state still referenced by a queued command. Catch C++ exceptions at the ABI boundary; they must not unwind through Rust.

The first test is: boot → ready → start an isolated bot match → read status → stop. Direct typed BotArena calls can replace string commands after this boundary is proven.

## Lifecycle limitations

- Global world/script/BotArena singletons make one engine per process the initial limit. A clean shutdown does not prove that restarting it in the same process is safe.
- `World::m_stopEvent` is static. Startup has `exit(1)` paths, and the worldserver freeze detector can abort the process. Rust cannot catch a native segmentation fault or abort.
- Authserver and worldserver both own signals, logging, configuration and database lifecycle. `shared/SharedDefines.cpp` also has a process-role global used by `shared/Secrets/SecretMgr.cpp`. Calling both existing mains concurrently is unsafe; auth consolidation is a separate refactor.
- Linking the engine does not remove its MySQL dependency. It also does not embed MPQs, world data or persistent player state in the executable.

A supervised engine worker provides a practical intermediate distribution format while retaining fault isolation. Keep the existing service deployment as rollback during development.

## Embedded database choice

**SQLite is the first candidate.** It preserves relational SQL and transactions, needs no database daemon, and is already used by the Rust host for `guests.sqlite`. It can be linked into a Rust executable even though its implementation is C. SQLite WAL allows readers alongside a writer, but only one write transaction at a time. Long reads can delay checkpoint progress; use local storage, short transactions and bounded queues. See [SQLite WAL](https://www.sqlite.org/wal.html) and [SQLite deployment guidance](https://www.sqlite.org/whentouse.html). Before a multi-connection WAL prototype, pin and verify the linked SQLite version: use 3.51.3 or newer, or a documented backport containing the [WAL-reset fix](https://www.sqlite.org/wal.html). Check `sqlite_version()` in the built runtime rather than assuming a Rust wrapper version implies a current SQLite library.

**redb** is a possible later typed Rust persistence backend. It offers ACID key-value storage with concurrent readers and one active write transaction. It would require replacing SQL queries, joins and indexes with application-level operations; no workload-specific performance advantage has been established. See the [redb project](https://github.com/cberner/redb) and [database API](https://docs.rs/redb/latest/redb/struct.Database.html).

**RocksDB** is an embedded ordered key-value engine, but introduces buffer/cache tuning and background flushing. It is not the first choice for simplifying this small relational game stack. See the [official operations guide](https://github.com/facebook/rocksdb/wiki/Basic-Operations).

There is no evidence yet that an embedded alternative will beat MySQL for this workload. Reducing daemon overhead and local IPC is a plausible benefit; concurrent writes and recovery behavior must be measured under equivalent durability settings.

## Why this is not a driver swap

Trinity's database layer is coupled to MySQL:

- `database/Database/MySQLConnection.cpp` uses `mysql_*` APIs directly.
- `database/Database/QueryResult.h` owns MySQL result, statement and bind structures.
- `database/Database/DatabaseWorkerPool.h` provides synchronous/asynchronous pools, prepared operations and transactions.
- `database/Database/Implementation/LoginDatabase.cpp` uses functions and syntax such as `UNIX_TIMESTAMP()`, `NOW()`, `CONCAT` and `ON DUPLICATE KEY UPDATE`.
- `CharacterDatabase.cpp` contains inventory/character persistence SQL. `game/Entities/Player/Player.cpp` groups character-save operations into transactions.
- `database/Updater/DBUpdater.cpp` invokes the external `mysql` executable for migrations.

A replacement therefore needs result/query abstraction changes, SQL/schema translation, transaction-parity checks, an import/migration pipeline and updates to the Rust host's own MySQL queries. Emulating the MySQL wire protocol would retain much of the complexity rather than establish a useful persistence boundary.

## Staged storage migration

1. Prove the linked engine lifecycle while retaining MySQL.
2. Prototype a versioned read-only world package with one narrow loader: `ObjectMgr::LoadItemTemplates` in `game/Globals/ObjectMgr.cpp`, plus BotArena gear loading. Compare IDs, row values, null handling and references against the existing loader.
3. Inventory every remaining world query and write. Separate mutable overlays before declaring world data read-only. Expand loader coverage incrementally.
4. Introduce typed operations for account/session/realm and character/inventory/talents/cooldowns persistence. Migrate callers and backend together, preserving transaction boundaries. SQLite WAL is the first backend to test; retain a MySQL rollback path.
5. Remove MySQL from runtime only after startup, gameplay, persistence and crash recovery reach parity. Build/import tooling can still consume TDB SQL without shipping a MySQL daemon in the game.

Static world data is already cached in memory: `ObjectMgr::LoadItemTemplates` fills `_itemTemplateStore`, and item lookups read that store. A different on-disk database therefore should not be advertised as accelerating each attack or spell.

## Prototype measurements

Use copied PvP data, dedicated test accounts, identical hardware and equivalent durability settings:

| Area | Measurements |
| --- | --- |
| Engine lifecycle | Boot-to-ready, command latency, total process-tree RSS/CPU, world tick p50/p95/p99 |
| Static package | Identical loaded-record hashes, startup duration, peak RSS, disk reads |
| Mutable storage | Account creation, character load/save and simultaneous reconnect/save bursts; transaction p50/p95/p99, queue depth, lock waits, throughput |
| Durability | WAL/checkpoint growth, termination during writes, reopen and verify complete inventory/talent/session transactions |

Do not combine engine embedding and database replacement in the first experiment. Separate changes make failures attributable and rollback practical.
