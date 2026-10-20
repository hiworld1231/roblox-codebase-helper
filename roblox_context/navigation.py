"""Deterministic metadata-only navigation files; never reads source blobs."""
from __future__ import annotations

from .store import SCRIPTS, atomic_text, realm


def paths(objects):
    result = {}
    def path(oid):
        if oid not in result:
            obj = objects[oid]
            result[oid] = (path(obj["parent"]) + "." if obj.get("parent") else "") + obj["name"]
        return result[oid]
    for oid in objects:
        path(oid)
    return result


def escape(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def script_index(store, sid):
    with store.lock:
        status, objects = store.status(sid), store.objects(sid)
    explorer = paths(objects)
    lines = ["# Script index", "", f"Place: {status['name']} ({status['place']}). Session: `{sid}`.",
             f"Plugin metadata sequence: {status['seq']}.", "",
             "This is a metadata snapshot, not proof of current Studio state. Check project_overview before use.",
             "No script source was read to generate this file. Studio owns these scripts; no filesystem source mapping exists.", "",
             "| Name | Type | Explorer path | Filesystem path | Realm | Evidence / limits | ID |",
             "|---|---|---|---|---|---|---|"]
    for oid in sorted(objects, key=lambda i: (explorer[i], i)):
        obj = objects[oid]
        if obj["className"] not in SCRIPTS:
            continue
        where, evidence = realm(obj, explorer[oid])
        evidence += "; plugin metadata; " + ("disabled" if obj.get("disabled") else "enabled or ModuleScript")
        lines.append("| " + " | ".join(map(escape, (obj["name"], obj["className"], explorer[oid], "Studio-only", where, evidence, oid))) + " |")
    return "\n".join(lines) + "\n"


def export_navigation(store, sid, check=False):
    workspace = store.workspace(sid)
    target = workspace / "docs/SCRIPT_INDEX.md"
    expected = script_index(store, sid)
    if check:
        return target.exists() and target.read_text(encoding="utf-8") == expected
    atomic_text(target, expected)
    objects, status = store.objects(sid), store.status(sid)
    explorer = paths(objects)
    project_map = workspace / "docs/PROJECT_MAP.md"
    if not project_map.exists():
        lines = ["# Project map", "", f"Observed test game: {status['name']} ({status['place']}).", "",
                 "## Observed entry-point candidates", "",
                 "Class/placement candidates only. Execution and gameplay responsibilities are unverified.", ""]
        lines += [f"- {escape(explorer[i])} ({o['className']})" for i, o in objects.items() if o["className"] in {"Script", "LocalScript"}]
        lines += ["", "## Observed communication objects", ""]
        lines += [f"- {escape(explorer[i])} ({o['className']})" for i, o in objects.items() if "Remote" in o["className"] or "Bindable" in o["className"]]
        lines += ["", "## Unverified architecture", "", "Module dependencies, runtime-created remotes, persistence and architectural decisions have not been inspected.",
                  "Use targeted graph_query/read_source, record evidence and update this map only for meaningful architectural changes."]
        atomic_text(project_map, "\n".join(lines) + "\n")
    current = workspace / "docs/CURRENT_TASK.md"
    if not current.exists():
        atomic_text(current, "# Current task\n\nNo task checkpoint recorded. Use task_checkpoint after decisions, edits and tests.\n")
    agents = workspace / "AGENTS.md"
    marker = "<!-- roblox-context-mcp -->"
    previous = agents.read_text(encoding="utf-8") if agents.exists() else "# Agent instructions\n"
    if marker not in previous:
        atomic_text(agents, previous.rstrip() + "\n\n" + marker + "\n"
                    "Start with docs/CURRENT_TASK.md and project_overview, then relevant PROJECT_MAP/SCRIPT_INDEX entries. "
                    "Search metadata first; read only necessary scripts and dependencies. Metadata/symbol search is incomplete for unindexed code. "
                    "Use explicit session IDs and revision-checked source ranges. Cached/offline results are not live evidence. "
                    "Use the existing official Studio MCP for edits, Play and runtime checks. Read edits back. "
                    "Do not install Rojo or a competing synchronizer. Do not repeat broad exploration without a reason. "
                    "Necessary deeper research, rereading and full verification remain allowed. "
                    "Keep reports/checkpoints compact. Update PROJECT_MAP only for architecture changes.\n")
    upgrade = "<!-- roblox-context-selective-v2 -->"
    current_agents = agents.read_text(encoding="utf-8")
    if upgrade not in current_agents:
        atomic_text(agents, current_agents.rstrip() + "\n\n" + upgrade + "\n"
                    "Resume an explicit session with project_overview(resume=True): identity, recorded checkpoint and coalesced changes in one call. "
                    "Paginate changes without repeating the checkpoint. Saved checks are not automatically verified. "
                    "Search metadata first; for code use project_search(search_in='source', scope_id=chosen_id). "
                    "At most 20 scripts are examined per page; follow nextCursor and unavailableSources before concluding absence. "
                    "Text matches are navigation hints, not dependency/runtime evidence. "
                    "Use read_source known_view only for matching session/object/hash/range whose actual text is STILL in the agent context. "
                    "Old-chat hashes or the server cache do not prove retained text. Necessary research and full tests remain unrestricted.\n")
    return True
