One-command automatic installation for Windows and Linux. All UI lives in Studio.

- Installs the read-only Studio panel, MCP connection and agent skill for Codex / Claude Code.
- Optional Claude Desktop connection on Windows.
- No Python installation needed for the portable binaries.
- Manual project connection; metadata-first indexing; no automatic full source scan.
- Automatic local database persistence and a private backup button.
- Codex and Claude can share the same authenticated bridge/cache without a separate daemon.

Windows PowerShell:
```powershell
irm https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.ps1 | iex
```
Linux x86_64:
```sh
curl -fsSL https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.sh | sh
```
Or download your platform binary and run it for automatic terminal setup.
Reconnect the AI client after setup. Studio: Plugins > Codebase > Connect this project.
If Studio was open, its local-plugin auto-reload may need enabling or one Studio restart.
Studio may ask you to allow localhost HTTP access. Roblox Studio on Linux requires
an existing Wine/Vinegar installation; this tool does not install Studio.
