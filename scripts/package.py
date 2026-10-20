#!/usr/bin/env python3
"""Whitelist a distributable archive; exclude all game/session/credential data."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from roblox_context.__main__ import build_plugin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT.parent / "roblox-context-mcp.zip")
    args = parser.parse_args()
    public = build_plugin(ROOT, ROOT / "build/RobloxContextMCP.rbxmx")
    files = [ROOT / name for name in ("README.md", "LICENSE", "AGENTS.md", "pyproject.toml", ".gitignore", "install.py", "install.sh", "install.ps1", "Install-Linux.sh", "Install-Windows.cmd")]
    for directory in ("roblox_context", "plugin", "scripts", "tests", "docs", "third_party", "skills", ".github", ".claude-plugin", ".codex-plugin"):
        files += [p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    files.append(public)
    private = ROOT / ".context/config.json"
    token = json.loads(private.read_text())["token"].encode() if private.exists() else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            raw = path.read_bytes()
            if token and token in raw:
                raise RuntimeError("Refusing to package a local credential")
            archive.writestr("roblox-context-mcp/" + path.relative_to(ROOT).as_posix(), raw)
    with zipfile.ZipFile(args.output) as archive:
        assert not any("/.context/" in n or "/projects/" in n for n in archive.namelist())
        assert archive.testzip() is None
        count = len(archive.namelist())
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".zip.sha256").write_text(checksum + "  " + args.output.name + "\n")
    print(json.dumps({"archive": str(args.output), "files": count, "bytes": args.output.stat().st_size, "privateDataIncluded": False}))


if __name__ == "__main__":
    main()
