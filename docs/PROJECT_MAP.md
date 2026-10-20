# Project map

This repository is Roblox developer tooling. Connected games have separate workspaces
under projects/PLACE/SESSION; their architecture must not be inferred from this map.

| Component | Responsibility |
|---|---|
| CLI / scripts/run.py | Explicit configuration, stdlib XML plugin build, MCP lifecycle |
| plugin/ContextPlugin.luau | Guarded Edit-only metadata/events, editor source on demand |
| roblox_context/bridge.py | Authenticated loopback, atomic snapshot intake, sequence fences and source jobs |
| roblox_context/store.py | Private SQLite revisions, selected sources, persistent analysis and checkpoints |
| roblox_context/_graph_base.py | Luau AST evidence, conservative resolution, hashes and uncertainty |
| roblox_context/service.py | Session-scoped search, graph, context, ranges, cursors and budgets |
| roblox_context/selective.py | Scoped literal source windows, sequence-bound cursors, coalesced metadata resume |
| roblox_context/runtime.py | One active bridge/database owner; authenticated forwarding and takeover for multiple AI clients |
| roblox_context/install.py | Automatic setup, profile discovery, client/skill merge and private plugin install |
| plugin/Panel.luau | Native Studio dock widget: explicit connection, metadata refresh and private database backup |
| roblox_context/mcp_server.py | Seven tools; compact JSON, no game write endpoints |
| roblox_context/navigation.py | Metadata-only script index and initial game workspace documents |

Data flow: Studio metadata -> acknowledged snapshot/deltas -> SQLite -> bounded MCP.
For a selected script: source job -> GetEditorSource -> private source/hash -> local
AST -> persisted extracted facts. Raw source is returned only on explicit range/context
request. No game RemoteEvents, RemoteFunctions, DataStores or gameplay systems are added.

Authority: current Studio edit-time state. Local cache/docs are navigation aids.
Source versions, command fences, sequence-gap invalidation and atomic snapshot completion
prevent silent reuse of incomplete data. Parser/grammar fingerprints invalidate analyses.
Topology changes conservatively re-resolve cached relationships; source ASTs are reused.

One MCP process owns HTTP and SQLite. Existing official Studio MCP owns game changes,
Play and runtime evidence. No process auto-starts BloxySync, no filesystem watcher,
and no index-output event can trigger a new index pass.

Important limits: lazy source coverage, conservative dynamic resolution, heuristic token
budgets, per-plugin-session IDs, explicit Test-place allowlist, no multiplayer acceptance.
WAL state may grow with deliberately fetched source versions; no automatic cache deletion
or whole-game scan runs in this release.

Selective retrieval retains the same bridge/plugin and dependencies. Metadata changes
store before/current paths inside existing JSON history; no database migration or
source scan is needed. Legacy rows retain explicit unknown paths. Source-search cache
population increments knowledge revision but not the Studio sequence used by its
cursor. Resume never loads source. Conditional views assert retained caller text;
they are not a server-side model memory. Per-place private profiles isolate the
original Untitled cache from the explicitly authorized read-only CSS connection.

0.3.0 distribution: Windows/Linux one-command bootstrap downloads a checksum-verified
portable executable; all UI lives in Studio. The installer registers existing seven
stdio tools and installs the shared agent skill. There is no setup website. New
installations are opt-in per Studio window and can index multiple places in isolated
workspaces; an optional explicit-place configuration still guards before collection.
Only an active MCP client's process owns HTTP/SQLite. Other clients authenticate to
that owner and forward seven whitelisted methods. If it exits, a remaining client can
take ownership and request a fresh metadata handshake. Backup uses SQLite's consistent
online backup API; it includes already cached code and never requests new source.
