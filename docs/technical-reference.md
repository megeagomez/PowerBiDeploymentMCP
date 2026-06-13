# Technical Reference

Developer-facing reference for the Power BI MCP Deployment server: architecture, tool schemas, metadata database, supported file formats, versioning internals, and development workflow.

For installation and everyday usage, see the [README](../README.md), the [Quick Start Guide](guia-inicio-rapido.md), and the [User Manual](user_manual.md).

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

## Available Tools

### Workspace Operations

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

### Semantic Model Operations

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

### Report Operations

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

### Metadata Operations

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

### Deployment Configuration Tools

- `configure_semantic_model_deployment`: Configure automatic deployment for semantic models
- `configure_report_deployment`: Configure automatic deployment with rebinding for reports
- `get_deployment_config`: Get saved deployment configuration
- `list_deployment_configs`: List all deployment configurations
- `setup_development_environment`: Quick setup for a complete dev environment

See [Deployment Configuration Guide](deployment-configuration.md) and [Configuration Example](deployment-configuration-example.md) for full walkthroughs.

### MCP Resources

- `config://server`: Server configuration and settings
- `auth://status`: Authentication status
- `metadata://stats`: Database statistics and health
- `deployments://recent`: Recent deployment operations
- `workspaces://summary`: Workspace summary with deployment history
- `deployments://{workspace}`: Full deployment history for a workspace
- `config://deployments`: All deployment configurations

### MCP Prompts

- `backup-workspace`: Interactive backup workflow
- `deploy-workspace`: Guided deployment between workspaces
- `sync-local-to-cloud`: Sync local files to Power BI
- `migrate-report`: Migrate report with rebinding
- `deployment-pipeline`: Dev → Test → Prod pipeline
- `configure-deployment`: Interactive deployment configuration

## Versioning Configuration

The server automatically detects Git repositories and applies versioning accordingly:

- **Inside Git repository**: No automatic versioning (rely on Git for version control)
- **Outside Git repository**: Automatic timestamp-based versioning (`filename_YYYYMMDD_HHMMSS.ext`)

To override automatic detection programmatically:

```python
from powerbi_mcp_server.metadata import VersioningConfig

config = VersioningConfig(
    enabled=True,  # Force enable versioning
    format="%Y%m%d_%H%M%S",  # Timestamp format
    db_path=Path("custom/path/metadata.duckdb")
)
```

Environment-variable based overrides are documented in [mcp-client-config.md](mcp-client-config.md).

## Authentication Internals

The server uses Device Flow authentication on first use. Tokens are cached securely using Windows DPAPI.

To manually re-authenticate programmatically:

```python
from powerbi_mcp_server.auth import get_authenticator

auth = get_authenticator()
auth.logout()  # Clear cached tokens
await auth.authenticate()  # Re-authenticate
```

## Metadata Database

The server uses DuckDB to track:

- **downloads**: Download history with versions, file paths, timestamps
- **uploads**: Upload history with asset IDs, operation types
- **workspace_mappings**: Local file to workspace asset mappings
- **report_model_relationships**: Report-to-semantic-model bindings

Database location: `~/.powerbi-mcp-deployment/metadata.duckdb` (or configured path via `POWERBI_MCP_DB_PATH`).

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
uv build
```

For diagnosing issues at runtime, see the [Troubleshooting Guide](troubleshooting.md).
