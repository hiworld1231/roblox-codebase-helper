# Roblox Codebase Helper

**Give Codex and Claude the right Roblox context, without reading your whole game.**

A read-only Studio panel, seven MCP tools and an agent skill. The initial index contains
script names, types and Explorer paths. Code is fetched only for selected scripts and
needed dependencies. No Rojo, file synchronization, embeddings or LLM indexing.

## Install with one command

**Windows — PowerShell**

```powershell
irm https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.ps1 | iex
```

**Linux x86_64 — terminal**

```sh
curl -fsSL https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.sh | sh
```

The command installs the Studio plugin, registers `roblox_context` in **Codex and
Claude Code**, and installs the agent skill. Existing client settings/other servers are
preserved. Portable builds include Python and the three runtime libraries; no Python,
Node or Rojo setup is needed. Scripts download the latest release and verify its SHA-256.
Inspect [install.sh](install.sh) / [install.ps1](install.ps1) before running if preferred.

The command configures Codex and Claude Code automatically. For only one client,
Linux users can pass `sh -s -- --clients codex` instead of `sh`. Claude Desktop can be
added with the downloaded executable's `--clients claude-desktop` option on Windows.
There is no setup website or browser wizard: all controls live in the Studio plugin.

Roblox Studio must already be installed/opened once. Linux support discovers existing
Vinegar/Wine Studio prefixes; it does not install Studio. Native Linux Studio is not
provided by Roblox. Ready-made Linux binary targets x86_64/glibc 2.35+.

## Then, three clicks

1. Reconnect MCP in **Codex / Claude**, or restart the client after setup.
2. In **Roblox Studio → Plugins → Codebase**, open the panel.
3. Click **Connect this project**. Allow localhost access if Studio asks.

That's it. No Place ID to copy, no token to paste. A project is indexed only after you
connect it. Sessions/places remain isolated; the agent must select the intended one.
The panel shows connection state, script count and how much code was fetched on demand.
**Refresh metadata index** reads no new source. **Back up database** makes a private
SQLite copy. The working database already saves automatically; you do not need to press
Save after every edit. The plugin never adds game objects, attributes, remotes or scripts.

If Studio was already open and local-plugin auto-reload is disabled, restart Studio once.
No setup page, always-on daemon or filesystem watcher is installed.

## The agent knows the workflow

The installer copies [the skill](skills/roblox-codebase-helper/SKILL.md) into the standard
Codex and Claude Code skill directories. Ask:

> Use roblox-codebase-helper. Find the scripts responsible for inventory, inspect the
> relevant dependencies and continue from the saved task checkpoint.

The skill teaches metadata-first search, explicit session selection, scoped code search,
coverage/uncertainty, small source ranges and task checkpoints. Claude Desktop receives
the same workflow through MCP instructions/tool descriptions; its local-MCP support is
separate from Claude Code skills. Claude Desktop on Linux is not an official target.

Both clients can run together: one client process owns the authenticated bridge/cache;
the other forwards tool requests to it. If the owner exits, a remaining client can take
over. No duplicate index daemon is started. Reconnect a project after takeover if its
fresh metadata snapshot has not arrived yet.

## How much context does it save?

In one **measured CSS project with 658 scripts**, startup read **zero source bytes**.
A selected console workflow fetched **4 scripts**, leaving **654 unread**.

| Measured operation | Ordinary read | Context workflow |
|---|---:|---:|
| Find one literal in a known console scope | 9921 bytes, 1 call | 1438 bytes, 1 call |
| Recheck 16 lines still retained by the agent | 2194 bytes, 1 call | 716 bytes, 1 call |

These are roughly **86%** and **67% less request/response context for those operations**,
using UTF-8 size as a heuristic. They are not account-quota measurements or guarantees
for a whole coding session. Adding the three recent features increased the seven-tool
schema by **884 bytes** (5340 total); schema/client caching costs are separate. Finding
an unknown scope costs additional queries, and a tiny exact direct read can be cheaper.
See [raw measurements](docs/CSS_BENCHMARK.json) and [validation](docs/VALIDATION.md).

## Tools

| Tool | Purpose |
|---|---|
| `project_overview` | Session selection, freshness, coverage; `resume=True` adds checkpoint and changes |
| `project_search` | Metadata; opt-in literal source search with explicit scope, <=20 scripts/page |
| `graph_query` | Dependencies, references, impact and diagnostics with evidence |
| `get_context` | Selected context/dependencies within a response budget |
| `read_source` | Exact edit-time lines; `known_view` suppresses text still retained by the agent |
| `changed_context` | Changes since a recorded revision |
| `task_checkpoint` | Task, decisions, checks, issues and next steps |

Use the **official Roblox Studio MCP** for game edits, Play and runtime tests. This helper
provides navigation/context, not an editing bridge. Necessary deeper research and full
verification remain unrestricted. Unread/dynamic/runtime dependencies stay explicitly
unknown. Static graphs do not certify runtime behavior.

## Other installation options

Source checkout requires Python 3.11+. No dependencies are installed into your global
Python or another project; setup creates its own local environment.

```sh
git clone https://github.com/hiworld1231/roblox-codebase-helper.git
cd roblox-codebase-helper
python3 install.py                         # automatic terminal setup
python3 install.py --cli --clients codex   # terminal, Codex only
```

Windows source users can open `Install-Windows.cmd`; Linux: `sh Install-Linux.sh`.
Use `--runtime-python /path/to/existing/python` to reuse a compatible environment
without installing libraries. `--plugin-dir PATH` chooses an ambiguous Studio profile.
`--place-id NUMBER` optionally restricts a fresh installation to one game.
`--language ru` selects Russian Studio labels in terminal setup.
[Setup details / removal](docs/INSTALLATION.md) · [API](docs/API.md)

The repository includes `.claude-plugin` / `.codex-plugin` skill manifests as an optional
skill distribution route. The one-command installer is the complete setup: manifests
alone cannot install a native Studio plugin or its private local credentials.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -q
python scripts/generate_index.py
python scripts/generate_index.py --check
```

GitHub Actions tests Windows/Linux and builds portable executables. Tag `v*` creates a
release only after both builds/tests succeed. [Architecture](docs/PROJECT_MAP.md).

MIT. The conservative Luau analyzer and inherited tests derive from BloxySync under
MIT; see [third-party license](third_party/BloxySync-LICENSE). Graphify provided design
inspiration; its package is not installed/copied. No game code or local database/token
belongs in this repository or its releases.
