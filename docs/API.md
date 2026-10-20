# Selective context API

All previous calls and seven tool names remain compatible. Restart/reconnect MCP to
load updated schemas. Feature changes do not require a new plugin build. Selecting a
different guarded place requires a private profile/build, as done for the user's CSS
read-only request. The plugin never writes game objects or source.

## Scoped literal source search

`project_search(session_id, text, search_in="source", scope_id, kind=None,
limit=20, cursor=None, budget_tokens=4000)`

Default search_in="metadata" preserves metadata/already-indexed-symbol search.
Source mode requires an object ID: a script itself or an ancestor container. It
searches only descendant Script/LocalScript/ModuleScript objects, optionally filtered
by one of those class names. Text is a nonempty, single-line literal (up to 1000
characters), Unicode case-insensitive; it is not a regular expression.

A page examines at most 20 scripts and returns at most `limit` matching lines,
grouped by objectId/path/sourceHash. Lines have 1-based numbers, match columns and
snippets of at most 180 characters; columns count Unicode code points. Explicit snippet bounds/truncation prevent
mistaking a window for a whole line. Long queries may extend beyond the snippet.
Roblox editor APIs use UTF-8 byte columns instead; convert before editing
([ScriptDocument reference](https://create.roblox.com/docs/reference/engine/classes/ScriptDocument)).
Sources go directly from Studio into the private local cache. Search does not build
a dependency graph or send full source to the agent.

`checkedScripts` counts scripts examined this page (a partly scanned script can
appear again); `completedScripts` is the cumulative scan position; `remainingScripts`
includes a partly scanned current script. `totalScripts` is the selected population.
`unavailableSources` identifies per-page failures. `complete` means traversal finished,
not that inaccessible source was searched. Follow nextCursor until exhausted and
retain earlier matches/failures. `absenceConfirmed` is deliberately conservative:
true only for a single complete, accessible, empty scan without a continuation.
An empty partial page cannot establish absence. A match is navigation evidence only.

Cursor binds exact query, kind, scope, session and acknowledged Studio sequence.
Cache filling may increment the knowledge revision without invalidating the cursor.
Scene/editor changes invalidate continuation; restart the query. Malformed cursors,
connection failures, sequence gaps and concurrent edits fail explicitly. Responses
respect the approximate JSON-byte budget or request a larger budget; no silent loss.

## Conditional source ranges

`read_source(..., known_view={"session": ..., "objectId": ..., "sourceHash": ...,
"startLine": 1, "endLine": 40})`

Supply fields from an earlier read **only while that actual text is still present
in the agent's current context**. A database cache, hash, checkpoint or previous chat
does not establish retention. This is a caller assertion, not server-side memory of
what a model remembers. Keep the original text when receiving `unchanged:true`.

Freshness and optional expected_revision checks run first. If session/object/hash
match and the requested available range is covered, the response contains compact
identity/hash/revision/range and unchanged:true, without lines. Other valid hints
fall back to ordinary lines. Invalid hints error. A changed source or uncovered range
never gets a false acknowledgement. Without known_view behavior is unchanged. Hint
request bytes count toward cost; use it for useful retained ranges, not every tiny read.

## Single-call task resume

`project_overview(session_id, resume=True, limit=20, cursor=None, budget_tokens=4000)`

An explicit session is mandatory. First page returns current project identity,
workspace, checkpoint and coalesced object changes since its recorded revision,
without requesting source or rebuilding the graph. New metadata events store before
and current paths, including descendants relocated by parent changes. firstChange,
lastChange and events preserve creation/deletion and repeated-edit meaning. Historic
rows without paths have pathsConfirmed:false and unknown paths.

Continuation is revision/sequence/checkpoint-bound and omits checkpoint. Source
indexing is reported separately as indexedObjects; it is not a gameplay edit.
Missing checkpoint: checkpointStatus=missing, changesStatus=no_checkpoint; no arbitrary
all-history scan. Offline/incomplete Studio: fresh=false, changesStatus=unavailable
with reason, while the saved checkpoint remains usable. Checkpoint checks are caller
records and have not been automatically rerun or verified. verifiedRevision remains
a legacy storage field meaning recorded revision, not test certification.

Budgets default to about 4000 tokens, estimated as ceil(UTF-8 compact JSON bytes/4).
This is a size heuristic, not model token accounting or account quota consumption.
Full investigations and verification can expand budgets when correctness requires it.
