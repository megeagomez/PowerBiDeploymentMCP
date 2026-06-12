## 1. Project Setup

- [x] 1.1 Create MCP server project structure with Python package layout
- [x] 1.2 Add MCP Python SDK dependency to requirements.txt
- [x] 1.3 Add DuckDB dependency to requirements.txt
- [x] 1.4 Configure Python package metadata (setup.py or pyproject.toml)
- [x] 1.5 Create main server entry point module
- [x] 1.6 Set up logging configuration for MCP server

## 2. Authentication Module

- [x] 2.1 Extract Device Flow authentication logic from pbi.py into dedicated auth module
- [x] 2.2 Implement token caching with DPAPI encryption for Windows
- [x] 2.3 Add token refresh logic with expiration detection
- [x] 2.4 Implement dual-scope token acquisition (Power BI + OneLake)
- [x] 2.5 Create authentication state management class
- [x] 2.6 Add user identity display after successful authentication

## 3. Core API Client

- [x] 3.1 Extract _request_with_retry function from powerbi_object_manager.py
- [x] 3.2 Create PowerBIClient class wrapping Power BI REST API calls
- [x] 3.3 Implement rate limiting with exponential backoff
- [x] 3.4 Add error translation from API errors to user-friendly messages
- [x] 3.5 Implement request logging for debugging

## 4. Workspace Operations

- [x] 4.1 Implement list_workspaces function with pagination support
- [x] 4.2 Implement get_workspace_by_name function with search capability
- [x] 4.3 Implement list_workspace_items function with type filtering
- [x] 4.4 Add workspace access validation logic
- [x] 4.5 Implement workspace details retrieval (capacity info, metadata)

## 5. Metadata and Versioning System

- [x] 5.1 Implement Git detection using gitpython or subprocess
- [x] 5.2 Create DuckDB schema for metadata tables (downloads, uploads, mappings, relationships)
- [x] 5.3 Implement metadata database initialization and migration logic
- [x] 5.4 Create MetadataManager class for database operations
- [x] 5.5 Implement automatic file versioning with timestamp suffixes
- [x] 5.6 Add configuration loading for versioning settings (enabled, format, db_path)
- [x] 5.7 Implement version history query functions
- [x] 5.8 Implement workspace mapping tracking
- [x] 5.9 Add report-to-semantic-model relationship tracking
- [x] 5.10 Implement metadata cleanup utilities

## 6. Semantic Model Operations

- [x] 6.1 Implement download_semantic_model for PBIX format using Power BI Export API
- [x] 6.2 Implement download_semantic_model for PBIP format using Fabric getDefinition API
- [x] 6.3 Implement format auto-detection for semantic models
- [x] 6.4 Integrate versioning logic into download operations
- [x] 6.5 Record download metadata to DuckDB after successful download
- [x] 6.6 Implement upload_semantic_model for PBIX format using Power BI Import API (multipart)
- [x] 6.7 Implement upload_semantic_model for PBIP format using Fabric Items + updateDefinition API
- [x] 6.8 Implement PBIP parts packaging (model.bim, metadata, config as Base64 payloads)
- [x] 6.9 Record upload metadata and workspace mapping after successful upload
- [x] 6.10 Add semantic model existence check and overwrite confirmation
- [x] 6.11 Implement streaming for large PBIX file downloads
- [x] 6.12 Add progress reporting for long-running uploads
- [x] 6.13 Validate PBIP structure before upload (required files present)

## 7. Report Operations

- [x] 7.1 Implement download_report for PBIR format using Fabric getDefinition API
- [x] 7.2 Implement download_report for legacy JSON format
- [x] 7.3 Implement format auto-detection for reports
- [x] 7.4 Integrate versioning logic into report download operations
- [x] 7.5 Record report download metadata to DuckDB
- [x] 7.6 Extract original semantic model connection from report definition (both formats)
- [x] 7.7 Implement upload_report for PBIR format using Fabric Items + updateDefinition API
- [x] 7.8 Implement upload_report for legacy JSON format
- [x] 7.9 Implement PBIR parts packaging (report.json, definition.pbir, StaticResources as Base64)
- [x] 7.10 Implement semantic model name matching algorithm
- [x] 7.11 Add rebinding prompt logic using MCP prompt/resource system
- [x] 7.12 Implement report rebinding to selected semantic model (update connection in definition)
- [x] 7.13 Record report-to-model relationship in metadata when rebinding occurs
- [x] 7.14 Record report upload metadata and workspace mapping
- [x] 7.15 Add report validation before upload (required files/structure present)
- [x] 7.16 Handle StaticResources folder for PBIR uploads

## 8. MCP Tool Definitions

- [x] 8.1 Define JSON schema for powerbi_authenticate tool
- [x] 8.2 Define JSON schema for powerbi_list_workspaces tool
- [x] 8.3 Define JSON schema for powerbi_list_workspace_items tool
- [x] 8.4 Define JSON schema for powerbi_download_semantic_model tool
- [x] 8.5 Define JSON schema for powerbi_upload_semantic_model tool
- [x] 8.6 Define JSON schema for powerbi_download_report tool
- [x] 8.7 Define JSON schema for powerbi_upload_report tool
- [x] 8.8 Define JSON schema for powerbi_query_version_history tool
- [x] 8.9 Define JSON schema for powerbi_query_workspace_deployments tool

## 9. MCP Tool Handlers

- [x] 9.1 Implement powerbi_authenticate tool handler
- [x] 9.2 Implement powerbi_list_workspaces tool handler
- [x] 9.3 Implement powerbi_list_workspace_items tool handler
- [x] 9.4 Implement powerbi_download_semantic_model tool handler with versioning and format detection
- [x] 9.5 Implement powerbi_upload_semantic_model tool handler with metadata tracking and format support
- [x] 9.6 Implement powerbi_download_report tool handler with versioning and format detection
- [x] 9.7 Implement powerbi_upload_report tool handler with rebinding, metadata, and format support
- [x] 9.8 Implement powerbi_query_version_history tool handler
- [x] 9.9 Implement powerbi_query_workspace_deployments tool handler

## 10. MCP Server Implementation

- [x] 10.1 Implement MCP server initialization and tool registration
- [x] 10.2 Add server configuration loading from MCP client settings
- [x] 10.3 Initialize metadata database on server startup
- [x] 10.4 Implement server lifecycle management (startup/shutdown)
- [x] 10.5 Add async execution support for long-running operations
- [x] 10.6 Implement authentication state persistence across server restarts
- [x] 10.7 Add structured error handling with MCP error format
- [x] 10.8 Implement server health check and readiness indicators

## 11. Testing Skills

- [x] 11.1 Create powerbi-mcp-test-authentication skill in .github/skills/
- [x] 11.2 Create powerbi-mcp-test-workspace-ops skill
- [x] 11.3 Create powerbi-mcp-test-semantic-model skill with versioning and format validation
- [x] 11.4 Create powerbi-mcp-test-report-rebind skill with metadata and format validation
- [x] 11.5 Create powerbi-mcp-test-metadata-tracking skill for DuckDB operations
- [x] 11.6 Implement test artifact management (setup/cleanup) functions
- [x] 11.7 Create test workspace configuration file
- [x] 11.8 Add test result reporting utilities

## 12. Documentation

- [x] 12.1 Create README.md with server installation instructions
- [x] 12.2 Document MCP client configuration (settings.json example)
- [x] 12.3 Document versioning system and Git detection behavior
- [x] 12.4 Document all supported formats (PBIX, PBIP, PBIR, legacy JSON) with examples
- [x] 12.5 Document metadata database schema and queries
- [x] 12.6 Document each tool with parameter descriptions and examples
- [x] 12.7 Create troubleshooting guide for common issues
- [x] 12.8 Document test workspace setup requirements
- [x] 12.9 Add architecture diagram showing component relationships

## 13. Integration Testing

- [x] 13.1 Execute powerbi-mcp-test-authentication skill and verify results
- [x] 13.2 Execute powerbi-mcp-test-workspace-ops skill and verify results
- [x] 13.3 Execute powerbi-mcp-test-semantic-model skill and verify versioning
- [x] 13.4 Test PBIX format download and upload
- [x] 13.5 Test PBIP format download and upload
- [x] 13.6 Test PBIR format download and upload
- [x] 13.7 Test legacy JSON report format
- [x] 13.8 Execute powerbi-mcp-test-report-rebind skill and verify metadata tracking
- [x] 13.9 Execute powerbi-mcp-test-metadata-tracking skill and verify DuckDB operations
- [x] 13.10 Test Git detection in both Git and non-Git directories
- [x] 13.11 Test versioning behavior with configuration overrides
- [x] 13.12 Test error scenarios (invalid credentials, missing workspaces)
- [x] 13.13 Validate rate limiting behavior under load
- [x] 13.14 Test concurrent tool invocations

## 14. Deployment

- [x] 14.1 Create package distribution configuration
- [x] 14.2 Add server startup script for different platforms
- [x] 14.3 Document MCP server registration with GitHub Copilot
- [x] 14.4 Create example configuration files with versioning settings
- [x] 14.5 Document metadata database backup and migration procedures
- [x] 14.6 Test installation on clean environment
