# Example MCP Client Configuration

This file shows example configurations for using the Power BI MCP server with various MCP clients.

## GitHub Copilot (VS Code)

Add to your VS Code settings (`settings.json`):

```json
{
  "github.copilot.chat.mcp.servers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "args": [],
      "env": {
        "POWERBI_MCP_DB_PATH": "${userHome}/.powerbi-mcp-deployment/metadata.duckdb",
        "POWERBI_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_DB_PATH": "C:\\Users\\YourUser\\.powerbi-mcp-deployment\\metadata.duckdb"
      }
    }
  }
}
```

## Custom MCP Client

```python
import asyncio
from mcp.client import Client

async def main():
    async with Client() as client:
        # Connect to Power BI MCP server
        await client.connect_stdio(
            command="powerbi-mcp-deployment",
            env={
                "POWERBI_MCP_DB_PATH": "/path/to/metadata.duckdb"
            }
        )
        
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}")
        
        # Call a tool
        result = await client.call_tool(
            "list_workspaces",
            arguments={}
        )
        print(f"Workspaces: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Environment Variables

All supported environment variables:

```bash
# Database path (default: ~/.powerbi-mcp-deployment/metadata.duckdb)
POWERBI_MCP_DB_PATH=/custom/path/metadata.duckdb

# Log level (default: INFO)
POWERBI_MCP_LOG_LEVEL=DEBUG

# Disable versioning (default: auto-detect from Git)
POWERBI_MCP_VERSIONING_ENABLED=false

# Custom timestamp format for versions (default: %Y%m%d_%H%M%S)
POWERBI_MCP_VERSION_FORMAT=%Y%m%d_%H%M

# Token cache directory (default: ~/.powerbi-mcp-deployment/cache)
POWERBI_MCP_CACHE_DIR=/custom/cache/dir
```

## Versioning Configuration

### Force Enable Versioning Everywhere

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_VERSIONING_ENABLED": "true"
      }
    }
  }
}
```

### Disable Versioning Everywhere

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_VERSIONING_ENABLED": "false"
      }
    }
  }
}
```

### Custom Timestamp Format

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_VERSION_FORMAT": "%Y-%m-%d_%H-%M-%S"
      }
    }
  }
}
```

Result: `sales_2024-01-15_14-30-45.pbix`

## Multi-workspace Configuration

For managing multiple Power BI environments:

```json
{
  "mcpServers": {
    "powerbi-dev": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_DB_PATH": "${userHome}/.powerbi-mcp-deployment/dev-metadata.duckdb",
        "POWERBI_MCP_CACHE_DIR": "${userHome}/.powerbi-mcp-deployment/dev-cache"
      }
    },
    "powerbi-prod": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_DB_PATH": "${userHome}/.powerbi-mcp-deployment/prod-metadata.duckdb",
        "POWERBI_MCP_CACHE_DIR": "${userHome}/.powerbi-mcp-deployment/prod-cache",
        "POWERBI_MCP_VERSIONING_ENABLED": "true"
      }
    }
  }
}
```

This allows separate:
- Metadata databases
- Token caches
- Versioning policies

## Debugging Configuration

For troubleshooting:

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_LOG_LEVEL": "DEBUG",
        "POWERBI_MCP_DB_PATH": "${workspaceFolder}/.powerbi-mcp-deployment-debug.duckdb"
      }
    }
  }
}
```
