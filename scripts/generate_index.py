#!/usr/bin/env python3
"""Export/check persisted metadata. Does not read Luau source or imply live freshness."""
from pathlib import Path
import argparse
import json
import sqlite3
import sys
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roblox_context.navigation import export_navigation
from roblox_context.store import Store
from roblox_context.store import atomic_text
from roblox_context.__main__ import config


def local_index(root):
    files = sorted((root / "plugin").rglob("*.luau"))
    metadata = [(p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns) for p in files]
    fingerprint = hashlib.sha256(json.dumps(metadata).encode()).hexdigest()
    lines = ["# Script index", "", "Local tooling sources; connected games have separate projects/PLACE/SESSION/docs indexes.",
             "Metadata fingerprint: `" + fingerprint + "`.", "",
             "| Name | Type | Filesystem path | Explorer location | Realm | Evidence |",
             "|---|---|---|---|---|---|"]
    for path, _, _ in metadata:
        entry = path == "plugin/ContextPlugin.luau"
        panel = path == "plugin/Panel.luau"
        lines.append("| " + Path(path).stem + " | " + ("Script" if entry else "Luau module (inlined)" if panel else "unverified") + " | " + path + " | " +
                     ("Studio local plugin / RobloxContextMCP" if entry or panel else "unmapped") + " | " +
                     ("Plugin / Edit" if entry or panel else "unknown") + " | " +
                     ("Explicit XML builder entry; filename/stat only" if entry else "Inlined by XML builder; filename/stat only" if panel else "Not included by the current builder; inspect before mapping") + " |")
    lines += ["", "Python files are host tools, not Roblox scripts. No source body was read for this index.",
              "Refresh after local add/delete/rename; check live project_overview before trusting a game snapshot."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--session", help="Omit to index the local tooling plugin instead")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.session:
        target = args.root / "docs/SCRIPT_INDEX.md"
        expected = local_index(args.root)
        ok = target.exists() and target.read_text(encoding="utf-8") == expected
        if not args.check:
            atomic_text(target, expected)
            ok = True
        print("Index matches metadata" if ok and args.check else "Index refreshed" if ok else "Index is stale")
        return 0 if ok else 1
    # Avoid Store.__init__: an offline index check must not invalidate a live session.
    store = Store.__new__(Store)
    import threading
    store.root = args.root.resolve()
    store.allowed_place = config(store.root)["placeId"]
    store.lock = threading.RLock()
    database = store.root / ".context/context.sqlite3"
    store.db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    store.db.row_factory = sqlite3.Row
    try:
        ok = export_navigation(store, args.session, args.check)
        print("Index matches persisted metadata" if args.check and ok else "Index refreshed" if ok else "Index is stale")
        return 0 if ok else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
