#!/usr/bin/env python3
"""Use an existing MCP/Luau runtime without installing this package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roblox_context.__main__ import main

if __name__ == "__main__":
    main()
