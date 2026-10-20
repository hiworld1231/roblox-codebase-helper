# Agent instructions

Preserve the user's project rules. This package is developer tooling, not gameplay.
Use English for maintained files; conversation may use the user's language.

Start with docs/CURRENT_TASK.md and relevant PROJECT_MAP/SCRIPT_INDEX entries, then
the current diff. Use targeted local rg searches. Read only necessary sources and
dependencies. Do not repeat a whole-project analysis without a concrete reason.
Deeper research, rereading and complete correctness checks remain allowed.

For a connected game, use project_overview and its session workspace/checkpoint first.
Verify place and Studio job identity against the selected official Studio MCP. Search
metadata, request a targeted graph, then necessary source ranges. Symbol/reverse-impact
coverage is incomplete until candidate source is explicitly indexed. Empty results are
not proof of absence. Dynamic links and static realm estimates are not runtime evidence.

Use the existing official Studio MCP for game edits and runtime tests. Read edits back.
Do not install Rojo, another synchronizer, embeddings or an LLM indexing worker. CSS read-only inspection through this plugin is now explicitly authorized by the user.
Never modify CSS game objects, sources, attributes or Play state. The active private
local acceptance profile is guarded to CSS/83440863421402; the original Untitled profile remains separate.
Public fresh installs use explicit per-window Connect before collection; no setup website.
Do not modify/rebind the existing BloxySync checkout or its unfinished changes.

Run relevant local tests and actual Studio tooling checks for affected behavior. Do not
skip verification to save context. Distinguish local, Studio Edit, Play, multiplayer and
published acceptance. Keep output/checkpoints concise; do not print whole indexes/logs.
Update PROJECT_MAP for architecture changes; replace obsolete CURRENT_TASK status.

Refresh/check local script metadata with `python scripts/generate_index.py --check`.
For game metadata, add `--session SESSION_ID`; --check compares saved metadata only,
not live Studio. The plugin refreshes that index on acknowledged metadata changes.

Source caches, credentials, session exports and private plugin builds live under
.context/ or projects/ and must not enter distributable packages. Do not log tokens
or full source. Preserve third-party attribution when reusing the Luau analyzer.

Resume an explicit session with project_overview(resume=True); this combines identity,
recorded checkpoint and compact metadata changes. Continuation pages omit checkpoint.
Recorded checks must not be presented as freshly verified tests. Source search requires
an explicit scope_id, examines at most 20 scripts/page and is literal/case-insensitive.
Follow continuation and unavailable-source records; partial emptiness proves no absence.
Text matches are investigation pointers, not dependency or runtime evidence.
Pass read_source known_view only if its actual text remains in the agent's context.
A stored hash/cache or checkpoint from an old chat does not establish retained text.

Distribution is terminal-first on Windows/Linux: install.sh / install.ps1. Keep the
Studio panel as the only user interface. Installer config merges must preserve other
MCP servers and personal preferences. Never put installed profiles, tokens, game code,
cache/backups or user-specific absolute paths in the public repo/release. Portable
builds bundle runtime dependencies; source setup creates its own environment or reuses
an explicitly supplied interpreter. Do not install build libraries into BloxySync.
