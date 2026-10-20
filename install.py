#!/usr/bin/env python3
"""Double-click / run for guided setup. MCP clients use the serve command internally."""
import sys
if '--root' in sys.argv[1:] or (len(sys.argv) > 1 and sys.argv[1] in ('serve', 'doctor', 'init', 'build-plugin')):
    from roblox_context.__main__ import main
else:
    from roblox_context.install import main
if __name__ == '__main__':
    main()
