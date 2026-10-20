"""Explicit setup, standalone XML plugin build, and one-process MCP runtime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import xml.etree.ElementTree as ET

from .store import Store, atomic_text

PACKAGE = Path(__file__).resolve().parents[1]


def config(root):
    path = root / ".context/config.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("Configuration must be private (chmod 600)")
    if not isinstance(value.get("token"), str) or len(value["token"]) < 32:
        raise ValueError("Invalid bridge credential")
    return value


def build_plugin(root, output, private=False):
    selected = config(root) if private else {"placeId": 73706828303910, "port": 38491, "token": ""}
    settings = {"language": selected.get("language", "en"), "autoConnect": selected.get("autoConnect", True), "placeId": selected["placeId"], "endpoint": "http://127.0.0.1:" + str(selected["port"]), "token": selected["token"]}
    # These controlled settings contain only decimal numbers and ASCII tokens/URL.
    encoded = "{ " + ", ".join(k + " = " + ("nil" if v is None else json.dumps(v)) for k, v in settings.items()) + " }"
    source = (PACKAGE / "plugin/ContextPlugin.luau").read_text(encoding="utf-8").replace("__CONTEXT_CONFIG__", encoded)
    panel = (PACKAGE / "plugin/Panel.luau").read_text(encoding="utf-8")
    source = source.replace("__CONTEXT_PANEL__", "(function()\n" + panel + "\nend)()")
    model = ET.Element("roblox", version="4")
    item = ET.SubElement(model, "Item", {"class": "Script", "referent": "RBXContextPlugin"})
    properties = ET.SubElement(item, "Properties")
    ET.SubElement(properties, "string", name="Name").text = "RobloxContextMCP"
    ET.SubElement(properties, "ProtectedString", name="Source").text = source
    output = Path(output)
    if output.suffix != ".rbxmx":
        raise ValueError("Use an .rbxmx output path")
    atomic_text(output, ET.tostring(model, encoding="unicode"), private=private)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PACKAGE)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--place-id", type=int, default=73706828303910)
    init.add_argument("--port", type=int, default=38491)
    build = commands.add_parser("build-plugin")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--private", action="store_true", help="Embed local credentials; never distribute this build")
    build.add_argument("--install-dir", type=Path, help="Explicit existing Studio local Plugins directory")
    commands.add_parser("serve")
    commands.add_parser("doctor")
    options = parser.parse_args(argv)
    root = options.root.resolve()
    try:
        if options.command == "init":
            if not (0 <= options.place_id) or not (1024 <= options.port <= 65535):
                raise ValueError("Invalid place ID or unprivileged port")
            path = root / ".context/config.json"
            if path.exists():
                raise ValueError("Configuration already exists; refusing to replace it")
            private = path.parent
            private.mkdir(parents=True, exist_ok=True, mode=0o700)
            private.chmod(0o700)
            atomic_text(path, json.dumps({"placeId": options.place_id, "port": options.port, "token": secrets.token_urlsafe(40)}, indent=2) + "\n", private=True)
            print("Initialized private local context configuration")
        elif options.command == "build-plugin":
            path = build_plugin(root, options.output, options.private)
            if options.install_dir:
                if not options.install_dir.is_dir() or not options.private:
                    raise ValueError("Installation requires an existing directory and --private")
                target = options.install_dir / "RobloxContextMCP.rbxmx"
                atomic_text(target, path.read_text(encoding="utf-8"), private=True)
                print("Installed guarded configured-place plugin: " + str(target))
            else:
                print("Built " + ("private " if options.private else "unconfigured ") + str(path))
        elif options.command == "doctor":
            value = config(root)
            print(json.dumps({"python": sys.executable, "root": str(root), "allowedPlaceId": value["placeId"], "port": value["port"], "credentials": "private", "runtime": "MCP process owns HTTP and SQLite"}))
        else:
            from .runtime import Runtime
            from .mcp_server import create_server
            runtime = Runtime(root, config(root))
            try:
                create_server(runtime).run(transport="stdio")
            finally:
                runtime.close()
    except (OSError, ValueError) as error:
        parser.exit(1, "Context MCP: " + str(error) + "\n")


if __name__ == "__main__":
    main()
