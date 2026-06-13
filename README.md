# Power BI MCP Deployment

A Model Context Protocol (MCP) server for managing Power BI assets including semantic models and reports. Supports all Power BI formats (PBIX, PBIP, PBIR, legacy JSON) with automatic versioning and metadata tracking.

> **¿Eres usuario de Power BI sin experiencia técnica?** Sigue la [Guía de Inicio Rápido](docs/guia-inicio-rapido.md) (en español), que explica cómo instalarlo y usarlo desde Claude Desktop paso a paso.

## Features

- **Multi-format support**: PBIX, PBIP, PBIR, and legacy JSON report formats
- **Automatic versioning**: Git-aware versioning with timestamp suffixes
- **Metadata tracking**: DuckDB-based metadata database for version history and deployment tracking
- **Authentication**: Device Flow authentication with secure DPAPI token caching
- **Report rebinding**: Intelligent semantic model matching for report uploads
- **Workspace operations**: List, search, and manage Power BI workspaces
- **🆕 Deployment Configuration**: Persistent configuration system for automated deployments
- **🆕 Auto-deployment**: Configure once, deploy automatically to the right workspace
- **🆕 Auto-rebinding**: Reports automatically rebind to configured semantic models
- **🆕 MCP Resources**: Server status, deployment history, and configuration monitoring
- **🆕 MCP Prompts**: Interactive workflows for backup, deployment, and migration

## What's New in v0.2.0

### Deployment Configuration System

The server now includes a **memory/configuration system** for automated deployments:

- **Deployment Profiles**: Define environments (dev, test, prod)
- **Semantic Model Configs**: Configure where each model should be deployed
- **Report Configs**: Configure where reports go and which semantic model they should use
- **Auto-rebinding**: Reports automatically connect to the correct semantic model

See [Deployment Configuration Guide](docs/deployment-configuration.md) for details.

### New Tools (5)

- `configure_semantic_model_deployment`: Configure automatic deployment for semantic models
- `configure_report_deployment`: Configure automatic deployment with rebinding for reports
- `get_deployment_config`: Get saved deployment configuration
- `list_deployment_configs`: List all deployment configurations
- `setup_development_environment`: Quick setup for a complete dev environment

### New Resources (7)

- `config://server`: Server configuration and settings
- `auth://status`: Authentication status
- `metadata://stats`: Database statistics and health
- `deployments://recent`: Recent deployment operations
- `workspaces://summary`: Workspace summary with deployment history
- `deployments://{workspace}`: Full deployment history for a workspace
- `config://deployments`: All deployment configurations

### New Prompts (6)

- `backup-workspace`: Interactive backup workflow
- `deploy-workspace`: Guided deployment between workspaces
- `sync-local-to-cloud`: Sync local files to Power BI
- `migrate-report`: Migrate report with rebinding
- `deployment-pipeline`: Dev → Test → Prod pipeline
- `configure-deployment`: Interactive deployment configuration

## Installation

### Prerequisites

- Power BI account with appropriate permissions
- Windows (for DPAPI token encryption)

### Recommended: run with `uvx` (no Python setup needed)

If you have [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed, no manual installation is needed — `uvx` downloads and runs the latest published version automatically. This is the recommended setup for MCP clients like Claude Desktop (see [Configuration](#configuration) below).

If you don't know what `uv` is, see the [Quick Start Guide for Power BI users](docs/guia-inicio-rapido.md) for a non-technical, step-by-step walkthrough.

### Install from PyPI

```powershell
pip install powerbi-mcp-deployment
```

### Install from source (for development)

```powershell
# Clone the repository
git clone https://github.com/megeagomez/PowerBiDeploymentMCP.git
cd PowerBiDeploymentMCP

# Install dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .
```

## Configuration

### MCP Client Setup

Add the Power BI MCP server to your MCP client configuration (e.g., Claude Desktop, GitHub Copilot) using `uvx`:

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "uvx",
      "args": ["powerbi-mcp-deployment"]
    }
  }
}
```

Or, if installed via pip:

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_DB_PATH": "C:\\path\\to\\metadata.duckdb"
      }
    }
  }
}
```

### Versioning Configuration

The server automatically detects Git repositories and applies versioning accordingly:

- **Inside Git repository**: No automatic versioning (rely on Git for version control)
- **Outside Git repository**: Automatic timestamp-based versioning (`filename_YYYYMMDD_HHMMSS.ext`)

To override automatic detection:

```python
from powerbi_mcp_server.metadata import VersioningConfig

config = VersioningConfig(
    enabled=True,  # Force enable versioning
    format="%Y%m%d_%H%M%S",  # Timestamp format
    db_path=Path("custom/path/metadata.duckdb")
)
```

## Usage

### Quick Start with Deployment Configuration

**1. Setup your development environment:**

```json
{
  "tool": "setup_development_environment",
  "arguments": {
    "workspace_name": "DEV - Analytics",
    "semantic_models": ["Sales Model", "Inventory Model"],
    "report_mappings": {
      "Sales Dashboard": "Sales Model",
      "Inventory Report": "Inventory Model"
    }
  }
}
```

**2. Upload assets (automatically uses saved configuration):**

```json
{
  "tool": "upload_semantic_model",
  "arguments": {
    "workspace_name": "DEV - Analytics",
    "source_path": "C:\\models\\sales.pbix"
  }
}
```

The server automatically:
- ✅ Detects this is "Sales Model"
- ✅ Uses the configured workspace
- ✅ Registers the deployment

**3. Upload reports (with automatic rebinding):**

```json
{
  "tool": "upload_report",
  "arguments": {
    "workspace_name": "DEV - Analytics",
    "source_path": "C:\\reports\\sales-dashboard"
  }
}
```

The server automatically:
- ✅ Detects this is "Sales Dashboard"
- ✅ **Rebinds to "Sales Model"** (from configuration)
- ✅ Uploads to the correct workspace
- ✅ Registers everything in metadata

See [Configuration Example](docs/deployment-configuration-example.md) for a complete walkthrough.

### Starting the Server

The server runs automatically when invoked by an MCP client (e.g., GitHub Copilot). For manual testing:

```powershell
powerbi-mcp-deployment
```

### Authentication

The server uses Device Flow authentication on first use:

1. Run any tool that requires authentication
2. Follow the device code prompt in your browser
3. Tokens are cached securely using Windows DPAPI

To manually re-authenticate:

```python
from powerbi_mcp_server.auth import get_authenticator

auth = get_authenticator()
auth.logout()  # Clear cached tokens
await auth.authenticate()  # Re-authenticate
```

### Available Tools

#### Workspace Operations

**list_workspaces**
```json
{
  "filter": "name eq 'My Workspace'"  // Optional OData filter
}
```

**get_workspace_contents**
```json
{
  "workspace_name": "My Workspace",
  "item_type": "SemanticModel"  // Optional: SemanticModel, Report, Dashboard
}
```

#### Semantic Model Operations

**download_semantic_model**
```json
{
  "workspace_name": "My Workspace",
  "dataset_name": "Sales Model",
  "target_path": "C:\\models\\sales.pbix",
  "format": "pbix"  // Optional: pbix or pbip
}
```

**upload_semantic_model**
```json
{
  "workspace_name": "My Workspace",
  "source_path": "C:\\models\\sales.pbix",
  "dataset_name": "Sales Model"  // Optional
}
```

**list_semantic_models**
```json
{
  "workspace_name": "My Workspace"
}
```

#### Report Operations

**download_report**
```json
{
  "workspace_name": "My Workspace",
  "report_name": "Sales Dashboard",
  "target_path": "C:\\reports\\sales",
  "format": "pbir"  // Optional: pbir or json
}
```

**upload_report**
```json
{
  "workspace_name": "My Workspace",
  "source_path": "C:\\reports\\sales",
  "report_name": "Sales Dashboard",  // Optional
  "rebind_to_model": "New Sales Model"  // Optional
}
```

#### Metadata Operations

**query_version_history**
```json
{
  "artifact_name": "Sales Model",
  "artifact_type": "SemanticModel"  // Optional
}
```

**query_deployments**
```json
{
  "workspace_name": "My Workspace"
}
```

## Architecture

```
powerbi_mcp_server/
├── __init__.py               # Package initialization
├── server.py                 # Main MCP server entry point
├── logging_config.py         # Logging configuration
├── auth/                     # Authentication module
│   ├── device_flow.py       # Device Flow implementation
│   ├── token_manager.py     # Token caching with DPAPI
│   └── authenticator.py     # High-level auth API
├── api/                      # API clients
│   ├── http_utils.py        # Retry logic and error handling
│   ├── client.py            # Power BI/Fabric API wrapper
│   ├── semantic_models.py   # Semantic model operations
│   └── reports.py           # Report operations
├── metadata/                 # Metadata and versioning
│   ├── git_utils.py         # Git detection
│   ├── database.py          # DuckDB schema and operations
│   ├── versioning.py        # Versioning logic
│   └── manager.py           # High-level metadata API
└── tools/                    # MCP tools
    ├── schemas.py           # Tool JSON schemas
    └── handlers.py          # Tool implementations
```

## Metadata Database

The server uses DuckDB to track:

- **downloads**: Download history with versions, file paths, timestamps
- **uploads**: Upload history with asset IDs, operation types
- **workspace_mappings**: Local file to workspace asset mappings
- **report_model_relationships**: Report-to-semantic-model bindings

Database location: `~/.powerbi-mcp-deployment/metadata.duckdb` (or configured path)

## Supported Formats

### PBIX (Power BI Desktop)
- Binary format for semantic models
- Downloaded using Power BI Export API
- Uploaded using Power BI Import API with multipart/form-data

### PBIP (Power BI Project)
- Folder structure with `model.bim`, `item.metadata.json`
- Downloaded/uploaded using Fabric getDefinition/updateDefinition APIs
- Base64-encoded parts in API payloads

### PBIR (Power BI Report)
- Folder structure with `report.json`, `definition.pbir`
- May include `StaticResources/` folder for images
- Downloaded/uploaded using Fabric getDefinition/updateDefinition APIs

### Legacy JSON (Report Definition)
- Single JSON file with report definition
- Legacy format, prefer PBIR for new reports

## Troubleshooting

### Authentication Issues

**Problem**: Token expired or invalid

**Solution**: Clear cached tokens and re-authenticate
```powershell
Remove-Item ~\.powerbi-mcp-deployment\cache\tokens.encrypted -Force
```

### Rate Limiting

**Problem**: HTTP 429 errors

**Solution**: The server automatically retries with exponential backoff (2^attempt seconds). If persistent, wait a few minutes.

### Workspace Not Found

**Problem**: "Workspace no encontrado"

**Solution**: 
- Verify workspace name is exact (case-sensitive)
- Ensure you have access permissions to the workspace
- Check workspace is not archived or deleted

### Git Detection Issues

**Problem**: Versioning not working as expected

**Solution**:
- Verify Git is installed and in PATH
- Check current directory is within/outside Git repository as expected
- Override with explicit `VersioningConfig(enabled=True/False)`

## Development

### Running Tests

```powershell
pytest tests/
```

### Code Formatting

```powershell
black powerbi_mcp_server/ --line-length 100
```

### Building Distribution

```powershell
python -m build
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please submit pull requests or open issues on GitHub.

## Support

For issues and questions:
- GitHub Issues: https://github.com/megeagomez/PowerBiDeploymentMCP/issues
