#!/usr/bin/env python
"""
Power BI MCP Server Startup Script

Cross-platform startup script for the Power BI MCP server.
"""

import sys

if __name__ == "__main__":
    from powerbi_mcp_server.server import main

    # main() is synchronous and calls asyncio.run() internally — wrapping it
    # again in asyncio.run() here would crash on exit ("a coroutine was
    # expected, got None") since main() itself returns None.
    try:
        main()
    except KeyboardInterrupt:
        print("\nPower BI MCP Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting Power BI MCP Server: {e}", file=sys.stderr)
        sys.exit(1)
