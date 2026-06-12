## Why

Power BI assets (semantic models and reports) are typically managed through the Power BI Service web interface, making it difficult to version control, automate deployments, and maintain consistency across environments. This creates challenges for teams wanting to implement CI/CD practices, track changes over time, and programmatically manage their BI infrastructure. A Model Context Protocol (MCP) server would enable developers to interact with Power BI assets through a standardized interface, allowing for version control integration, automated deployments, and better collaboration workflows.

## What Changes

- Create an MCP server that exposes Power BI asset management capabilities
- Implement Device Flow authentication for secure user-based access
- Enable download/upload of semantic models in all formats (.pbix legacy binary, .pbip Power BI Projects)
- Enable download/upload of reports in all formats (legacy JSON, .pbir Power BI Reports)
- Support automatic format detection and conversion where appropriate
- Support versioning of Power BI assets through local file storage with DuckDB metadata tracking
- Provide workspace discovery and management operations
- Reuse existing authentication and API logic from `pbi.py` and `powerbi_object_manager.py`
- Include comprehensive testing infrastructure with VS Code skills for validation against real workspaces

## Capabilities

### New Capabilities
- `authentication`: Device Flow authentication to obtain Power BI API tokens and manage credentials
- `semantic-model-operations`: Upload and download semantic models to/from Power BI workspaces, supporting both .pbix and .pbip formats
- `report-operations`: Upload and download reports with interactive rebinding to target semantic models in the destination workspace
- `workspace-operations`: List, query, and discover workspaces and their contents
- `metadata-management`: Version tracking and metadata management using DuckDB with automatic versioning for downloads outside Git repositories
- `mcp-server`: MCP server implementation exposing all operations as tools with proper schema definitions
- `testing-skills`: VS Code skills that validate all MCP operations against a test workspace

### Modified Capabilities
<!-- No existing capabilities are being modified -->

## Impact

- **New Files**: MCP server implementation, schema definitions, tool handlers
- **Reused Code**: Authentication logic from `pbi.py`, object management from `powerbi_object_manager.py`
- **Dependencies**: 
  - Existing Python dependencies (msal, requests, etc.)
  - MCP SDK for server implementation
  - Power BI REST API and Fabric API endpoints
- **Testing**: New VS Code skills will be created to test all MCP operations end-to-end
- **User Workflow**: Users can now version control and deploy Power BI assets programmatically through GitHub Copilot or other MCP clients
