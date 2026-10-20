"""Portable setup, native Studio plugin discovery and non-destructive client registration."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import venv

from .__main__ import build_plugin, config
from .store import atomic_text

SOURCE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
MARKER = 'roblox-codebase-helper'


def data_root():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'RobloxCodebaseHelper'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/RobloxCodebaseHelper'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / MARKER


def plugin_directories(home=None, platform=None, environ=None):
    home, platform, env = Path(home or Path.home()), platform or sys.platform, os.environ if environ is None else environ
    candidates = []
    if platform == 'win32':
        candidates.append(Path(env.get('LOCALAPPDATA', home / 'AppData/Local')) / 'Roblox/Plugins')
    elif platform == 'darwin':
        candidates.append(home / 'Documents/Roblox/Plugins')
    else:
        for base in (home / '.var/app/org.vinegarhq.Vinegar/data/vinegar/prefixes', home / '.local/share/vinegar/prefixes'):
            candidates.extend(base.glob('*/drive_c/users/*/AppData/Local/Roblox/Plugins'))
        if env.get('WINEPREFIX'):
            candidates.extend(Path(env['WINEPREFIX']).glob('drive_c/users/*/AppData/Local/Roblox/Plugins'))
    return sorted({p.resolve() for p in candidates if p.is_dir() or p.parent.is_dir()})


def client_paths(home=None):
    env = {} if home is not None else os.environ
    home = Path(home or Path.home())
    codex = Path(env.get('CODEX_HOME', home / '.codex')) / 'config.toml'
    if sys.platform == 'darwin':
        desktop = home / 'Library/Application Support/Claude/claude_desktop_config.json'
    elif sys.platform == 'win32':
        desktop = Path(env.get('APPDATA', home / 'AppData/Roaming')) / 'Claude/claude_desktop_config.json'
    else:
        desktop = Path(env.get('XDG_CONFIG_HOME', home / '.config')) / 'Claude/claude_desktop_config.json'
    return {'codex': codex, 'claude-code': home / '.claude.json', 'claude-desktop': desktop}


def owned(entry):
    text = json.dumps(entry).lower()
    return MARKER in text or 'roblox-context-mcp' in text or 'robloxcodebasehelper' in text or 'roblox codebase helper' in text


def render_client(path, client, command, args):
    """Return merged text. Never replace unrelated servers or malformed configurations."""
    old = path.read_text(encoding='utf-8') if path.exists() else ''
    entry = {'command': str(command), 'args': list(args)}
    if client == 'codex':
        import tomllib
        parsed = tomllib.loads(old) if old else {}
        existing = parsed.get('mcp_servers', {}).get('roblox_context')
        if existing and not owned(existing):
            raise ValueError('An unrelated roblox_context entry already exists in Codex; rename it before installing')
        # Preserve every unrelated byte/section; remove only our server and nested tables.
        lines, output, skip = old.splitlines(keepends=True), [], False
        for line in lines:
            if re.match(r'^\s*\[', line):
                header = line.strip()
                skip = bool(re.match(r'^\[mcp_servers\.(?:roblox_context|"roblox_context")(?:\.|\])', header))
            if not skip:
                output.append(line)
        block = '\n[mcp_servers.roblox_context]\ncommand = ' + json.dumps(str(command), ensure_ascii=False) + '\nargs = ' + json.dumps(list(args), ensure_ascii=False) + '\n'
        text = ''.join(output).rstrip() + '\n' + block
        tomllib.loads(text)
        return text
    value = json.loads(old) if old.strip() else {}
    if not isinstance(value, dict) or not isinstance(value.get('mcpServers', {}), dict):
        raise ValueError('Client config must be a JSON object with mcpServers')
    servers = value.setdefault('mcpServers', {})
    if servers.get('roblox_context') and not owned(servers['roblox_context']):
        raise ValueError('An unrelated roblox_context entry already exists; rename it before installing')
    if client == 'claude-code':
        entry['type'] = 'stdio'
    servers['roblox_context'] = entry
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def copy_payload(destination):
    """Only tool code/assets. Never copy private profiles, game sources, caches or Git state."""
    destination.mkdir(parents=True, exist_ok=True)
    for directory in ('roblox_context', 'plugin', 'scripts', 'skills'):
        src = SOURCE / directory
        if src.exists():
            shutil.copytree(src, destination / directory, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.context', 'projects'))
    for name in ('pyproject.toml', 'LICENSE'):
        if (SOURCE / name).exists():
            shutil.copy2(SOURCE / name, destination / name)


def install(*, clients, plugin_dir, root=None, runtime_python=None, language='en', place_id=None, progress=lambda text: None, home=None):
    root = Path(root or data_root()).resolve()
    client_home = home
    home = Path(home or Path.home())
    plugin_dir = Path(plugin_dir).expanduser().resolve()
    if not clients or any(c not in client_paths(client_home) for c in clients):
        raise ValueError('Select at least one supported AI client')
    if not plugin_dir.is_dir() and not plugin_dir.parent.is_dir():
        raise ValueError('Studio Plugins folder not found. Open Studio once, or select its actual Plugins folder')
    if language != 'en' or (place_id is not None and (type(place_id) is not int or place_id < 0)):
        raise ValueError('Invalid language or place ID')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    settings_path = root / '.context/config.json'
    if settings_path.exists():
        settings = config(root)
    else:
        import socket
        port = 38491
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        settings = {'placeId': place_id, 'port': port, 'token': secrets.token_urlsafe(40), 'autoConnect': False, 'language': language}
    settings.update(language=language, autoConnect=False)
    # Do not replace a running owner's code under its feet.
    import socket
    with socket.socket() as probe:
        probe.settimeout(.3)
        if probe.connect_ex(('127.0.0.1', settings['port'])) == 0 and (root / 'install.json').exists():
            raise ValueError('Close/reconnect the running MCP clients before updating this installation')
    frozen = bool(getattr(sys, 'frozen', False))
    app = root / 'app'
    if frozen:
        command = root / 'bin' / ('codebase-helper.exe' if sys.platform == 'win32' else 'codebase-helper')
        args = ['--root', str(root), 'serve']
    else:
        command = Path(runtime_python).expanduser().absolute() if runtime_python else root / 'runtime' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        args = [str(app / 'scripts/run.py'), '--root', str(root), 'serve']
    # Validate client files and skill collisions before any configuration mutation.
    plans = [(client_paths(client_home)[client], render_client(client_paths(client_home)[client], client, command, args)) for client in clients]
    skill_paths = []
    if 'codex' in clients:
        skill_paths.append(home / '.agents/skills' / MARKER)
    if any(c.startswith('claude') for c in clients):
        skill_paths.append(home / '.claude/skills' / MARKER)
    source_skill = SOURCE / 'skills' / MARKER
    for target in skill_paths:
        if target.exists() and not (target / '.codebase-helper-managed').exists():
            raise ValueError('Skill destination already exists and is not managed by this installer: ' + str(target))
    progress('Preparing local runtime')
    if frozen:
        command.parent.mkdir(parents=True, exist_ok=True)
        if Path(sys.executable).resolve() != command.resolve():
            temporary = command.with_suffix(command.suffix + '.new')
            shutil.copy2(sys.executable, temporary); temporary.replace(command)
        command.chmod(0o700)
    else:
        if runtime_python:
            check = subprocess.run([str(command), '-c', 'import mcp,tree_sitter,tree_sitter_luau'], capture_output=True)
            if check.returncode:
                raise ValueError('Selected Python needs mcp, tree-sitter and tree-sitter-luau')
        else:
            if not command.exists():
                venv.EnvBuilder(with_pip=True).create(root / 'runtime')
            progress('Installing the three required libraries')
            result = subprocess.run([str(command), '-m', 'pip', 'install', 'mcp==1.26.0', 'tree-sitter==0.25.2', 'tree-sitter-luau==1.2.0'], capture_output=True)
            if result.returncode:
                atomic_text(root / '.context/install.log', result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'), private=True)
                raise ValueError('Runtime setup failed. See the private .context/install.log; retry after checking Python/network access')
        copy_payload(app)
    progress('Installing the read-only Studio plugin')
    settings_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings_path.parent.chmod(0o700)
    atomic_text(settings_path, json.dumps(settings, indent=2) + '\n', private=True)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    target = plugin_dir / 'RobloxContextMCP.rbxmx'
    if target.exists() and target.read_text(encoding='utf-8') != '':
        atomic_text(root / '.context/previous-plugin.rbxmx', target.read_text(encoding='utf-8'), private=True)
    build_plugin(root, target, private=True)
    progress('Connecting AI clients and installing the agent skill')
    for path, text in plans:
        if path.exists():
            atomic_text(root / '.context' / ('backup-' + str(len(list((root / '.context').glob('backup-*')))) + '-' + path.name), path.read_text(encoding='utf-8'), private=True)
        atomic_text(path, text, private=True)
    for target in skill_paths:
        shutil.copytree(source_skill, target, dirs_exist_ok=True)
        atomic_text(target / '.codebase-helper-managed', 'Managed by roblox-codebase-helper\n')
    record = {'version': '0.3.1', 'root': str(root), 'clients': list(clients), 'plugin': str(plugin_dir / 'RobloxContextMCP.rbxmx'),
              'command': str(command), 'args': args, 'skills': [str(p) for p in skill_paths], 'language': language, 'automaticSourceScan': False}
    atomic_text(root / 'install.json', json.dumps(record, indent=2) + '\n', private=True)
    progress('Installed. Reconnect your AI clients, then connect the project in Studio.')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', action='store_true')
    parser.add_argument('--clients', default='codex,claude-code')
    parser.add_argument('--plugin-dir', type=Path)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--runtime-python', type=Path)
    parser.add_argument('--language', choices=('en',), default='en')
    parser.add_argument('--place-id', type=int)
    options = parser.parse_args(argv)
    directories = plugin_directories()
    selected = options.plugin_dir or (directories[0] if len(directories) == 1 else None)
    if selected is None:
        parser.error('Specify --plugin-dir (automatic detection found zero or multiple Studio profiles)')
    try:
        result = install(clients=options.clients.split(','), plugin_dir=selected, root=options.data_dir,
            runtime_python=options.runtime_python, language=options.language, place_id=options.place_id, progress=print)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Setup: ' + str(error) + '\n')
