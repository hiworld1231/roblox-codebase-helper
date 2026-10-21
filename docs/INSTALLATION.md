# Installation and recovery

One-command installers and portable binaries are linked in the README. Supported
ready-made targets: Windows x86_64 and Linux x86_64 (glibc 2.35+). A source setup uses
Python 3.11+ and can also run on macOS, but no macOS binary/native acceptance is claimed.

## What setup changes

- User data directory: Windows `%LOCALAPPDATA%/RobloxCodebaseHelper`; Linux
  `$XDG_DATA_HOME/roblox-codebase-helper` or `~/.local/share/roblox-codebase-helper`.
- MCP server `roblox_context`: Codex `~/.codex/config.toml` (or CODEX_HOME), Claude Code
  `~/.claude.json`; optional Windows Claude Desktop config under `%APPDATA%/Claude`.
- Agent skill: `~/.agents/skills/roblox-codebase-helper` and `~/.claude/skills/roblox-codebase-helper`.
  Unrelated existing skill folders are not overwritten.
- Agent guidance: a delimited managed block in `~/.codex/AGENTS.md` / `~/.claude/CLAUDE.md` tells agents
  to prefer `roblox_context` for reads over the official Studio MCP. Other text in those files is preserved.
- One native plugin: `RobloxContextMCP.rbxmx` in the actual Studio Plugins folder.
- Previous client configuration/plugin copies: private `.context/backup-*` and
  `.context/previous-plugin.rbxmx` inside the tool data directory.

No changes to gameplay, system Python, other MCP servers, Rojo or existing BloxySync.
Fresh setup is manual opt-in per Studio window; source is never bulk-read on connect.
Existing explicit-place installations keep their configured place restriction.
On Unix the private data/config/backup modes are restricted to the user. Windows uses
user-profile directory ACLs; Unix mode bits are not treated as Windows ACL verification.

## Finding Studio

Windows: `%LOCALAPPDATA%/Roblox/Plugins`. Linux discovers existing Flatpak/native
Vinegar studio prefixes, or a provided WINEPREFIX. When several profiles exist, use `--plugin-dir PATH`; setup never guesses which
unrelated profile to overwrite. Open Studio at least once before installing.

Studio may ask for localhost HTTP permission. Denial leaves an explicit disconnected
state. If local-plugin auto-reload is disabled, restart Studio after installation.
The server starts with the AI client's MCP connection; no startup service is installed.

## Updating

Close/reconnect running MCP connections before running setup again. Setup is idempotent;
keeps credentials/database and other client settings. Two clients share the bridge at
one configured loopback port. Another application's occupied port is not taken over.
A new installation chooses a free port if the preferred one is occupied.

## Backup and restore

The active SQLite database saves automatically after acknowledged changes. The Studio
button makes an online-consistent SQLite backup in `.context/backups/` and displays
its path. It includes all sessions in that installation and already fetched code;
keep it private. Making the backup fetches no additional source.

To restore: close MCP connections, copy the chosen backup over `.context/context.sqlite3`,
remove only its old `context.sqlite3-wal` / `context.sqlite3-shm` sidecars, then reconnect.
A complete live metadata handshake is still required; restored data is never treated
as evidence of a connected Studio. Credentials live separately in config.json.

## Remove

Remove only the `roblox_context` entry from the clients you selected; preserve other
servers/settings. Remove `RobloxContextMCP.rbxmx` from that Studio Plugins directory
and the two managed skill folders. Delete the tool data directory if you no longer
need its cache/backups/checkpoints. The official Studio MCP remains independent.

## Claude clients

Claude Code uses user-scoped local stdio MCP configuration and skills. Claude Desktop
uses its `mcpServers` JSON config and the server's built-in tool/workflow instructions;
copying a Claude Code skill alone does not activate a Desktop extension. Web Claude
cannot access this loopback-only stdio server as a remote cloud connector.

References: [Claude Code MCP](https://code.claude.com/docs/en/mcp),
[Claude Desktop local MCP](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).
