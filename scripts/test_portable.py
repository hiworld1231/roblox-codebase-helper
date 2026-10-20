#!/usr/bin/env python3
"""Exercise frozen CLI, isolated installation and installed MCP without user config writes."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory() as temp:
        for args in (['--help'], ['--root', temp, 'init'], ['--root', temp, 'doctor'],
                     ['--root', temp, 'build-plugin', '--output', str(Path(temp) / 'plugin.rbxmx')]):
            result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
        assert 'RobloxCodebaseHelper' in (Path(temp) / 'plugin.rbxmx').read_text(encoding='utf-8')
        sandbox = Path(temp) / 'home'
        sandbox.mkdir()
        plugins = Path(temp) / 'Studio Plugins'
        plugins.mkdir()
        data = Path(temp) / 'installed'
        env = {**os.environ, 'HOME': str(sandbox), 'USERPROFILE': str(sandbox),
               'CODEX_HOME': str(sandbox / '.codex'), 'APPDATA': str(sandbox / 'AppData/Roaming'),
               'LOCALAPPDATA': str(sandbox / 'AppData/Local')}
        result = subprocess.run([binary, '--cli', '--clients', 'codex,claude-code', '--plugin-dir', str(plugins),
                                 '--data-dir', str(data)], env=env, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        record = json.loads((data / 'install.json').read_text())
        assert (sandbox / '.agents/skills/roblox-codebase-helper/SKILL.md').exists()
        assert (sandbox / '.claude/skills/roblox-codebase-helper/SKILL.md').exists()
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def check():
            params = StdioServerParameters(command=record['command'], args=record['args'])
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    assert len((await session.list_tools()).tools) == 7
                    value = await session.call_tool('project_overview', {})
                    assert json.loads(value.content[0].text)['sessions'] == []
        asyncio.run(check())
        print(json.dumps({'frozenCLI': True, 'frozenPluginResources': True, 'portableInstall': True,
                          'installedFrozenMCP': True, 'sevenTools': True, 'actualUserConfigChanged': False}))


if __name__ == '__main__':
    main()
