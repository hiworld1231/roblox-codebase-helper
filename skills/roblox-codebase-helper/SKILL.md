---
name: roblox-codebase-helper
description: Use for Roblox Studio projects connected through roblox_context MCP. Navigate metadata, scoped code search, dependencies and task checkpoints without repeatedly reading the entire game. Official Studio MCP handles game edits and Play.
---

# Roblox Codebase Helper

Use this skill for connected Roblox work. These tools only read Studio and save local
context. Never invent architecture or claim completeness from unindexed code.

1. Call `project_overview()` to discover sessions. Select the intended place and Studio
   job explicitly; never silently choose the newest session or another open game.
2. Call `project_overview(session_id=..., resume=True)` for identity, saved checkpoint
   and coalesced changes in one request. Follow nextCursor. Checkpoint checks are
   caller records, not automatically rerun tests. Read relevant PROJECT_MAP/SCRIPT_INDEX
   entries in the returned workspace; do not load the whole index by default.
3. Search names/paths using `project_search(session_id, text)`. It does not read unseen
   code. If code search is needed, select a script/container ID explicitly, then use
   `search_in="source", scope_id=...`. Search is literal and case-insensitive. A page
   examines at most 20 scripts and returns bounded line windows. Follow nextCursor and
   unavailableSources: empty partial output is not proof of absence. Text matches are
   investigation hints, not proof of dependencies or executed behavior.
4. Use `graph_query` and `get_context` on relevant IDs. For callers/impact, include
   candidate callers in analyze_ids. Unread, dynamic and runtime-created dependencies
   remain unknown. Expand the investigation when correctness requires it.
5. Read only necessary ranges with `read_source`; expected_revision detects stale
   assumptions. Supply known_view={session,objectId,sourceHash,startLine,endLine} only
   when that actual text STILL exists in your current context. A cache/hash or old
   chat is not retained text. unchanged:true reuses that retained range without lines.
6. Use the separately connected official Roblox Studio MCP for edits/Play. Confirm
   the same place/job, read before editing, read edits back, and run appropriate full
   checks. This context plugin does not supply a write/play interface or replace tests.
7. Save concise task_checkpoint records: task, decisions, changedFiles, checks, issues,
   nextSteps. Record actual evidence and open gaps. Update PROJECT_MAP only for meaningful
   architecture changes. No broad re-exploration without a concrete reason.

Default budgets are approximate 4000 tokens; raise them for necessary analysis/debugging.
Never economize by skipping checks. Source-cache bytes are not account quota usage.

## Connection and recovery

Install using the repository's guided installer, selecting your AI client. In Studio,
Plugins > Codebase opens the panel. Click Connect this project. Initial indexing reads
metadata only. No manual Place ID is needed by the default opt-in installation.
If disconnected, open/reconnect roblox_context in Codex or Claude and retry. Different
clients share one authenticated bridge/database; no extra daemon is needed. Play
pauses edit-time indexing. Sequence gaps require a metadata refresh. Never treat saved
files/offline cache as a fresh full Studio index.

The database saves automatically. Back up database in the Studio panel creates a private
local SQLite copy including cached code; do not upload it, local tokens, or game sources.
