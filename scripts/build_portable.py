#!/usr/bin/env python3
"""Build only tools/resources into a portable setup + MCP executable."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--name',required=True);args=p.parse_args()
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name',args.name,
 '--collect-submodules','mcp.server','--copy-metadata','mcp','--copy-metadata','tree-sitter','--copy-metadata','tree-sitter-luau','--collect-all','tree_sitter_luau','--collect-submodules','roblox_context',
 '--hidden-import','tree_sitter','--hidden-import','tomllib']
for directory in ('plugin','skills'):
 command += ['--add-data',f'{ROOT/directory}:{directory}']
command += ['--add-data',f'{ROOT/"LICENSE"}:.','--add-data',f'{ROOT/"roblox_context/_graph_base.py"}:roblox_context',str(ROOT/'install.py')]
subprocess.run(command,cwd=ROOT,check=True)
output=ROOT/'dist'/args.name
if not output.exists() and output.with_suffix('.exe').exists():output=output.with_suffix('.exe')
output.with_name(output.name+'.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
