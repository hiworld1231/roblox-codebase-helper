# Validation

## 0.3.0 installation/panel pass

55 local tests pass (48 previous + seven installation/runtime tests). Preserves unrelated
Codex TOML / Claude JSON servers and preferences; rejects malformed/colliding configs;
handles paths with spaces and real Wine/Vinegar discovery; setup/reinstall runs against
an isolated fake home. Shared clients use one bridge/database and can take ownership
when the first client exits. SQLite backup passes integrity_check and preserves source
revision without fetching game code. Fresh opt-in multi-place workspaces remain separate.

Actual local terminal setup found the installed Studio profile, installed the plugin,
registered Codex and Claude Code, and copied both agent skills. A native PluginGuiService
inspection confirmed the dock widget, project identity, labelled buttons and real layout.
Native desktop input/screenshot access is not available in the current host; do not claim
an independently scored pixel review or a button-click acceptance from a viewport capture.
The temporary browser setup page was removed at the user's explicit request; no website
is part of installation. Frozen Windows/Linux acceptance is recorded by the release CI.


## Selective improvements and authorized CSS read-only pass, 2026-10-20

- **48 local tests pass: all original 36 plus 12 selective scenarios.** Existing real
  MCP stdio test additionally exercises source search, known_view and single-call resume.
- Scoped search: duplicate names, explicit container scope, 20-script page ceiling,
  literal/Unicode matching, long-line windows, budget boundaries, line continuation,
  cache-only revision changes, edit-invalidated cursors and inaccessible sources.
- Conditional views: covered range, changed body, wrong object/session/hash, new range,
  stale revision and offline state; false unchanged acknowledgements are rejected.
- Resume: coalesced parent rename/reparent/delete paths, legacy unknown paths,
  pagination without checkpoint repetition, missing checkpoint, offline/restart and
  separate sessions. No source reads are performed by resume.
- Native Untitled: two disabled same-name scripts, paged source search, retained range,
  rename/deletion history, cleanup to the original 15 script paths/classes. Temporary
  helper plugin removed. Native automation did not retain the requested unsaved editor
  text in this pass, so **new source-search handling of genuinely unsaved editor text
  is not claimed as newly native-verified**. Version/text changes pass local tests;
  unchanged collector still uses GetEditorSource. The earlier collector/editor evidence
  below remains separate from this new-mode acceptance.
- On explicit user request, selected a separate exact-place CSS profile and private
  plugin configuration. CSS was read only: no game object/source/attribute or Play
  changes. Initial native plugin snapshot: **658 scripts / 903 metadata objects**, with
  **0 source reads / 0 source bytes**. Classes: 19 Script, 56 LocalScript, 583 ModuleScript.
- CSSConsole search found OutputSelection at line 12, agreeing with a complete selected
  script read through official Studio MCP. Scoped lookup read one script; dependency
  inspection fetched three more and found three static require edges. 654 sources
  remain unread and reverse/runtime graph completeness is unverified.
- CSS retained lines 1..16 yielded unchanged:true with no code. Resume returned identity,
  checkpoint and changes in one call with no source. Idle interval: zero additional
  source reads, source bytes, metadata batches and graph builds.

## Current measurements

See CSS_BENCHMARK.json for normalized request + response sizes, call counts and result
completeness. Scope is already known in both workflows; JSON-RPC framing is excluded.
No game source is distributed with these aggregate results.

| CSS task | Ordinary / previous workflow | Improved workflow |
|---|---:|---:|
| Literal lookup in selected console script | 9921 bytes, 1 call | 1438 bytes, 1 call |
| Recheck retained lines 1..16 | 2194 bytes, 1 call | 716 bytes, 1 call |

Seven-tool schema: **4456 -> 5340 bytes (+884)**. These schema bytes are separate
from calls. A conservative one-task charge of the entire new seven-tool schema makes
that scoped lookup 1438 + 5340 = 6778 bytes; charging only the feature delta gives
1438 + 884 = 2322 bytes. Client schema caching and actual account-limit consumption
were not measured. No fixed percentage is promised.

Reproducible small fixture measurements in improvements-benchmark.json include requests
and parsed result payloads. Literal lookup: 4 calls -> 1; task continuation: 3 -> 1;
conditional read: 1 -> 1. Sizes include hint-request overhead. Run
`python scripts/benchmark_selective.py` with an optional `--baseline-schema FILE` to
compare a separately captured prior tools list. Small efficient direct reads can win.

## Original implementation evidence (historical pass)

Date: 2026-10-20. Test place: Untitled Game, 73706828303910. Studio Edit only.

## Passed

- 36 local tests, including real MCP SDK stdio and authenticated HTTP. Source ranges,
  dynamic/ambiguous dependencies, invalid Luau, cycles, add/delete/rename/reparent,
  persistent parse cache, stale revisions/cursors, session isolation, incomplete
  snapshots, metadata-only file generation and competing-launch safety are covered.
- All seven MCP tools loaded through the SDK; actual search, context, source and
  checkpoint calls succeeded. Codex's roblox_context entry is enabled and points
  to the already installed dependency runtime. No dependencies were installed.
- Real Studio initial inventory: 15 existing scripts, zero source reads. Only two
  owned fixture scripts were selected for source/graph tests; original code was not scanned.
- Live require/remote-fire evidence, known-caller reverse impact, stable ID after
  rename/reparent, script changes and durable changed_context results passed.
- Native ScriptDocument edits appeared through read_source. Immediate native probes
  separately confirmed editor text can differ from Script.Source. Production reads
  GetEditorSource and never substitutes Source for an inaccessible editor buffer.
- Deferred document close was reproduced as a closed-document error, repaired with
  retained document identity, then retested: closing invalidated the old revision
  and no new closed-document error appeared after the fixed plugin loaded.
- Six temporary scene objects and the temporary editor-probe plugin were removed.
  Final native and MCP inventory: 15 original scripts, one original RemoteEvent,
  no fixture. Original paths/classes/parents/RunContext/enabled/source-version metadata
  matched the baseline. This is metadata verification, not a bulk source-hash audit.
- In a live idle interval, source reads, source bytes, metadata batches and graph
  builds all increased by zero. Only the requested freshness fence increased.
- Both local and game metadata indexes pass --check. XML bundles were built without
  Rojo; the public build has an empty credential and exits until privately configured.

## Measured response sizes

UTF-8 tool text bytes, not account tokens. Context responses use compact JSON.
Request/tool-schema/startup overhead is excluded. New tools include identity, revision
and coverage fields; ordinary source text is not semantically identical to a graph.

| Scenario | Ordinary Studio MCP | Context MCP |
|---|---:|---:|
| Find existing VoiceJumpEvent | 132 bytes, 1 call | 739 bytes, 1 call |
| Inspect selected caller/module, targeted 7-line reads | 503 bytes, 2 calls | 1062 bytes, 1 graph call |
| Same caller using default entire-file read | 5358 bytes, 1 call | 1062 bytes, 1 graph call |
| Resume after a known caller edit, exact changed line already known | 57 bytes, 1 call | 1147 bytes, delta + range calls |

The fixture includes 60 comment lines, deliberately showing the cost of unnecessary
whole-file reads. Small efficient direct reads can be cheaper. The main benefits are
bounded graph retrieval, persistent task context, zero initial source scan and avoiding
repeated source/analysis work. No universal percentage or account-limit saving is claimed.
For a known exact line, use an efficient direct range instead of requesting a full graph.
Raw aggregate measurements are in benchmark.json; private native/protocol evidence is
under .context and is excluded from the distributable archive.

## Explicit boundaries

No game Play, multiplayer, publishing, production-place change, full-game dependency
coverage or account-usage measurement. DataStore extraction passed local AST tests;
no live DataStore was accessed. Other places require explicit separate configuration.
The existing desktop chat's tool inventory predates this registration; new connections
load the enabled MCP entry. The server is hosted by the client, not an always-on daemon.

The installed MCP SDK emits a Pydantic forward-reference warning on Python 3.14 during
startup; the tested protocol still works. No third-party runtime was modified to hide it.
