"""Setup must preserve unrelated clients; UI backup never mutates game state."""
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from roblox_context.install import install, plugin_directories, render_client
from roblox_context.runtime import Runtime
from roblox_context.store import Store, ContextError
from roblox_context.bridge import Bridge


class InstallationTests(unittest.TestCase):
    def test_codex_merge_preserves_other_tables_and_reinstall(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config.toml'
            p.write_text('model = "configured-model"\n[mcp_servers.other]\ncommand = "existing"\n[projects."a b"]\ntrust_level = "trusted"\n')
            result=render_client(p,'codex','/opt/roblox-codebase-helper/python',['a b','serve'])
            p.write_text(result)
            same=render_client(p,'codex','/opt/roblox-codebase-helper/python',['a b','serve'])
            self.assertEqual(same,result)
            import tomllib
            parsed=tomllib.loads(same)
            self.assertEqual(parsed['model'],'configured-model')
            self.assertEqual(parsed['mcp_servers']['other']['command'],'existing')
            self.assertEqual(parsed['mcp_servers']['roblox_context']['args'],['a b','serve'])
            self.assertEqual(parsed['projects']['a b']['trust_level'],'trusted')

    def test_json_clients_preserve_servers_and_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'claude.json';p.write_text(json.dumps({'mcpServers':{'other':{'command':'keep'}},'theme':'light'}))
            for client in ('claude-code','claude-desktop'):
                result=json.loads(render_client(p,client,'/bin/roblox-codebase-helper',['serve']))
                self.assertEqual(result['theme'],'light')
                self.assertEqual(result['mcpServers']['other'],{'command':'keep'})
                self.assertEqual(result['mcpServers']['roblox_context']['command'],'/bin/roblox-codebase-helper')

    def test_collision_and_malformed_config_fail_without_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config';p.write_text('{bad json')
            with self.assertRaises(ValueError):render_client(p,'claude-code','x',[])
            self.assertEqual(p.read_text(),'{bad json')
            p.write_text('[mcp_servers.roblox_context]\ncommand = "unrelated"\n')
            with self.assertRaises(ValueError):render_client(p,'codex','x',[])
            self.assertIn('unrelated',p.read_text())

    def test_windows_and_vinegar_detection_handles_spaces(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)/'User Space';native=home/'AppData/Local/Roblox/Plugins';native.mkdir(parents=True)
            self.assertEqual(plugin_directories(home,'win32',{}),[native.resolve()])
            linux=home/'.var/app/org.vinegarhq.Vinegar/data/vinegar/prefixes/studio/drive_c/users/user/AppData/Local/Roblox/Plugins';linux.mkdir(parents=True)
            self.assertEqual(plugin_directories(home,'linux',{}),[linux.resolve()])

    def test_complete_setup_installs_skill_and_guarded_plugin_without_source(self):
        import sys
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)/'home';plugins=home/'Studio Plugins';plugins.mkdir(parents=True)
            root=Path(temp)/'Roblox Codebase Helper'
            with patch.dict('os.environ',{},clear=True):
                result=install(clients=['codex','claude-code'],plugin_dir=plugins,root=root,home=home,runtime_python=sys.executable)
                again=install(clients=['codex','claude-code'],plugin_dir=plugins,root=root,home=home,runtime_python=sys.executable)
            settings=json.loads((root/'.context/config.json').read_text())
            self.assertIsNone(settings['placeId'])
            self.assertFalse(settings['autoConnect'])
            self.assertEqual(result['args'],again['args'])
            self.assertTrue((home/'.agents/skills/roblox-codebase-helper/SKILL.md').exists())
            self.assertTrue((home/'.claude/skills/roblox-codebase-helper/SKILL.md').exists())
            self.assertIn('RobloxCodebaseHelper',(plugins/'RobloxContextMCP.rbxmx').read_text())
            self.assertFalse((root/'app/.context').exists())
            self.assertFalse((root/'.context/context.sqlite3').exists())

    def test_multi_place_workspace_and_private_consistent_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp),None)
            try:
                for sid,place in [('session-one',11),('session-two',22)]:
                    store.hello(sid,place,'job','game');store.ingest(sid,0,[{'id':'root','name':'game','className':'DataModel'}],snapshot=True)
                    self.assertEqual(store.workspace(sid).parts[-2],str(place))
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                bridge=Bridge(store,'x'*40,port)
                try:
                    result=bridge.dispatch('/ui/backup',{'session':'session-one'})
                    target=Path(result['path'])
                    copy=sqlite3.connect(target)
                    try:
                        self.assertEqual(copy.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                        self.assertEqual(copy.execute('select count(*) from sessions').fetchone()[0],2)
                    finally:copy.close()
                    self.assertEqual(store.status('session-one')['revision'],1)
                finally:bridge.http.server_close()
            finally:store.close()

    def test_shared_owner_two_clients_and_takeover(self):
        with tempfile.TemporaryDirectory() as temp:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            settings={'placeId':None,'token':'y'*40,'port':port}
            one=Runtime(Path(temp),settings);two=Runtime(Path(temp),settings)
            try:
                self.assertIsNone(two.bridge)
                self.assertEqual(two.overview(),one.overview())
                with self.assertRaises(ContextError) as error:two.overview('missing-session')
                self.assertEqual(error.exception.code,'unknown_session')
                one.close();one=None
                self.assertEqual(two.overview()['sessions'],[])
                self.assertIsNotNone(two.bridge)
            finally:
                if one:one.close()
                two.close()
