#!/usr/bin/env python3
"""Run the actual published one-command install in an isolated home and fake Studio profile."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'home'
    home.mkdir()
    local = home / 'AppData/Local'
    env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home),
           'CODEX_HOME': str(home / '.codex'), 'APPDATA': str(home / 'AppData/Roaming'),
           'LOCALAPPDATA': str(local), 'XDG_DATA_HOME': str(home / '.local/share')}
    if sys.platform == 'win32':
        plugin = local / 'Roblox/Plugins'
        data = local / 'RobloxCodebaseHelper'
        command = ['powershell', '-NoProfile', '-NonInteractive', '-Command',
                   'irm https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.ps1 | iex']
    else:
        plugin = home / '.var/app/org.vinegarhq.Vinegar/data/vinegar/prefixes/studio/drive_c/users/test/AppData/Local/Roblox/Plugins'
        data = home / '.local/share/roblox-codebase-helper'
        command = ['sh', '-c', 'curl -fsSL https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.sh | sh']
    plugin.mkdir(parents=True)
    result = subprocess.run(command, env=env, cwd=temp, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    record = json.loads((data / 'install.json').read_text())
    assert Path(record['command']).is_file()
    assert (plugin / 'RobloxContextMCP.rbxmx').is_file()
    assert (home / '.agents/skills/roblox-codebase-helper/SKILL.md').is_file()
    assert (home / '.claude/skills/roblox-codebase-helper/SKILL.md').is_file()
    assert (home / '.codex/config.toml').is_file() and (home / '.claude.json').is_file()
    print(json.dumps({'publishedBootstrap': True, 'platform': sys.platform,
                      'installedVersion': record['version'], 'isolatedHome': True, 'actualUserConfigChanged': False}))
