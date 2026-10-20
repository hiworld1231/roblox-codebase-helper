# Current task

0.3.0: terminal-first Windows/Linux setup, native Studio panel and an agent skill.
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

## Remaining verification

Verify Windows/Linux frozen release builds and one-command downloaded binary setup in
CI before calling the public bootstrap ready. Record native UI interaction/screenshot
limits separately; a game viewport screenshot is not panel visual acceptance. Existing
unsaved-editor search acceptance remains unconfirmed, as documented in VALIDATION.md.
Reconnect clients after setup. No CSS game objects/sources/attributes/Play state were
changed. Existing BloxySync checkout/dependencies are not modified.
