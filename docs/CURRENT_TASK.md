# Current task

0.3.4: terminal-first Windows/Linux setup, native Studio panel and an agent skill.
The user explicitly rejected a browser installer; it was removed. All product UI
lives in Roblox Studio. Publish to hiworld1231/roblox-codebase-helper.

## Changes and decisions

- One curl / PowerShell command downloads a checksum-verified portable build, installs
  the native plugin, registers Codex + Claude Code and installs the agent skill.
- Source fallback uses isolated dependencies or an explicitly supplied interpreter.
- Optional Claude Desktop registration; other servers/preferences are preserved.
- Fresh installs require Connect this project before metadata collection. Optional
  explicit-place guards remain. No automatic full-source scan or gameplay write API.
- Native dock: real connection/index counts, refresh, disconnect and private SQLite
  backup. Database persistence is automatic. No setup website, cloud index or daemon.
- Concurrent Codex/Claude sessions share one owner/cache, with takeover on owner exit.
- Skills and optional native agent-plugin manifests document selective investigation,
  task resume, revision checks, evidence and complete verification.

## Evidence / checks

- 55 local tests pass: original 48 + client merge/collision, detection, real isolated
  setup/reinstall, per-place workspaces, SQLite backup, concurrent clients/takeover.
- Local automatic setup installed into the standard tool data directory, found the
  existing Vinegar Studio Plugins folder, registered both clients and installed skills.
- Native Studio panel exists under PluginGuiService and has real layout/status/buttons.
  Its UI objects are outside the game's DataModel. Local acceptance remains CSS-read-only.
- Previous 658-script CSS context measurements remain in CSS_BENCHMARK.json; no new
  account-quota claim or fixed whole-session percentage is made.

## Release acceptance

- Published v0.3.3 portable executables for Windows x86_64 and Linux x86_64.
- Both platform builds pass all 55 tests, frozen CLI/resource checks, isolated automatic
  installation and seven-tool MCP startup from the installed executable.
- Actual published curl and Windows PowerShell one-command installers both pass against
  isolated homes and Studio profiles: GitHub Actions run 39471518738.
- Release build evidence: GitHub Actions run 39470931538. Bootstrap uses the updated
  main-branch scripts with built-in .NET SHA-256 verification for Windows PowerShell.
- Product UI, skill and documentation are English only. No browser installer exists.

## Connection behavior and limits

After Connect this project, connection failures retry automatically with backoff while
MCP runs. Newly created scripts, renames, moves and deletions update metadata automatically;
source changes invalidate selected cached code. New source is fetched only on demand.
Fresh Studio/plugin sessions require explicit Connect again. Client configuration/schema
updates require reconnecting MCP once. No daemon keeps it running after all clients exit.
Native panel objects/layout/status were inspected, but full native button/pixel visual
acceptance is not claimed. Existing unsaved-editor search acceptance remains unconfirmed.
CSS game objects/sources/attributes/Play state were not changed. Existing BloxySync
checkout/dependencies remain unchanged.

## Agent preference for this MCP (unreleased)

Agents defaulted to the official Studio MCP for reads. Server instructions, tool
descriptions and skill description now direct reads to roblox_context; the installer
adds an idempotent managed block to global Codex AGENTS.md / Claude CLAUDE.md
(user text preserved). 56 local tests pass. Not yet verified with live agents;
existing installs need a reinstall and MCP reconnect.
