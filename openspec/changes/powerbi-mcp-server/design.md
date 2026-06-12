## Context

Currently, Power BI asset management requires manual interaction through the web portal or complex custom scripts. The existing codebase (`pbi.py` and `powerbi_object_manager.py`) provides Python utilities for authentication and workspace/object creation, but these are not exposed through a standardized protocol. 

This design proposes creating an MCP server that wraps the existing Python functionality and exposes it as MCP tools, enabling any MCP client (like GitHub Copilot) to programmatically manage Power BI assets. The solution will leverage the existing Device Flow authentication and Power BI REST API integration.

**Current Constraints:**
- Python 3.x environment with existing dependencies (msal, requests, azure-identity)
- Power BI REST API and Fabric API rate limits
- Device Flow authentication requires user interaction for first-time setup
- MCP protocol requirements for tool schema definitions

**Stakeholders:**
- Power BI developers wanting to version control assets
- DevOps teams implementing CI/CD for BI solutions
- Data teams needing programmatic deployment capabilities

## Goals / Non-Goals

**Goals:**
- Create a Python-based MCP server exposing Power BI operations as tools
- Reuse existing authentication and API logic from the current codebase
- Support upload/download of semantic models (.pbix, .pbip formats)
- Support upload/download of reports with optional rebinding
- Enable workspace discovery and querying
- Provide interactive prompts for rebinding decisions during report uploads
- Implement automatic versioning for downloads when not under Git control
- Track deployment metadata using DuckDB for version history and workspace mapping
- Include comprehensive testing through VS Code skills

**Non-Goals:**
- Full-featured Power BI IDE capabilities (focus on asset management only)
- Real-time collaboration features
- Dashboard operations (not used in typical workflows, focus on semantic models and reports)
- Support for legacy Power BI Desktop .pbix editing (only upload/download)
- Automatic schema migration or data refresh scheduling
- Built-in Git integration (may be added in future versions, not MVP)

## Decisions

### 1. MCP Server Architecture
**Decision:** Implement as a Python-based MCP server using the MCP Python SDK

**Rationale:** 
- Existing codebase is Python-based, allowing maximum code reuse
- MCP Python SDK provides standardized server implementation patterns
- Python's async capabilities work well with MCP's async tool execution model

**Alternatives Considered:**
- TypeScript MCP server: Would require rewriting all API logic
- REST API wrapper: Doesn't fit MCP protocol requirements

### 2. Authentication Strategy
**Decision:** Use Device Flow for interactive authentication, cache tokens in secure storage

**Rationale:**
- Device Flow already implemented in `pbi.py` (`get_bearer_token_interactive()`)
- Enables headless authentication suitable for MCP servers
- Works across desktop and remote scenarios
- Aligns with Microsoft's recommended approach for CLI tools

**Alternatives Considered:**
- Client credentials flow: Requires service principal setup, less user-friendly
- Interactive browser flow: Doesn't work well in server contexts

### 3. Tool Structure
**Decision:** Expose separate tools for each major operation category:
- `powerbi_authenticate`: Establish authenticated session
- `powerbi_list_workspaces`: Discover available workspaces
- `powerbi_download_semantic_model`: Download a semantic model to local storage
- `powerbi_upload_semantic_model`: Upload a semantic model to a workspace
- `powerbi_download_report`: Download a report definition
- `powerbi_upload_report`: Upload a report with optional rebinding prompt
- `powerbi_list_workspace_items`: List contents of a workspace
- `powerbi_query_version_history`: Query version history for an asset
- `powerbi_query_workspace_deployments`: Query deployment history for a workspace

**Rationale:**
- Granular tools enable better composability in agent workflows
- Clear separation of concerns for each operation
- Easier to test individual operations
- Follows MCP best practices for tool design

**Alternatives Considered:**
- Single tool with operation parameter: Less discoverable, harder to validate schemas
- Auto-combined operations: Reduces flexibility for advanced workflows

### 4. Rebinding Strategy for Reports
**Decision:** Use MCP's resource/prompt system to ask user for rebinding decisions

**Rationale:**
- MCP protocol supports interactive prompts for user input
- Allows intelligent defaults (search for matching semantic model names)
- User maintains control over critical binding decisions

**Implementation:**
- When uploading a report, detect original semantic model connection
- Search target workspace for semantic models
- If matches found, present options via MCP prompt
- If no matches or user declines, upload with original connection

### 5. File Format Support
**Decision:** Support all Power BI format variations for complete compatibility

**Semantic Models:**
- **.pbix** (legacy): Single binary file, uses Power BI REST API Import/Export endpoints
- **.pbip** (Power BI Project): Folder structure with separate files (model.bim, item.metadata.json, item.config.json, .pbi/ folder), uses Fabric Items API with getDefinition/updateDefinition

**Reports:**
- **Legacy JSON**: Single JSON file with complete report definition, uses Power BI REST API
- **.pbir** (Power BI Report): Folder structure (report.json, definition.pbir, item.metadata.json, StaticResources/), uses Fabric Items API with getDefinition/updateDefinition

**Rationale:**
- Full backward compatibility with existing assets
- Support modern development workflows with PBIP/PBIR
- Both formats actively used in production environments
- Different API endpoints required for different formats

**API Mapping:**
- PBIX download: `POST /v1.0/myorg/groups/{groupId}/reports/{reportId}/Export`
- PBIX upload: `POST /v1.0/myorg/groups/{groupId}/imports` (multipart/form-data)
- PBIP/PBIR download: `POST /v1/workspaces/{workspaceId}/items/{itemId}/getDefinition`
- PBIP/PBIR upload: `POST /v1/workspaces/{workspaceId}/semanticModels` or `/reports` + `updateDefinition`

**Implementation Details:**
- Auto-detect format from file/folder structure
- Handle definition parts packaging for PBIP/PBIR (Base64 encoding)
- Preserve folder structure during download
- Validate all required files present before upload

### 6. Code Reuse Strategy
**Decision:** Extract and adapt functions from `pbi.py` and `powerbi_object_manager.py` into MCP tool handlers

**Specific Reuse Targets:**
- `get_bearer_token_interactive()` → authentication tool
- `PowerBIObjectManager` class methods → workspace/object operations
- `_request_with_retry()` → resilient API calls
- Notebook upload pattern (Base64 encoding, updateDefinition) → PBIP/PBIR uploads

**Rationale:**
- Proven, working code for Power BI interactions
- Rate limiting already handled
- Base64 encoding pattern established for definition parts
- No need to reinvent API patterns

### 7. Testing Approach
**Decision:** Create VS Code skills that execute real operations against a designated test workspace

**Structure:**
- Skill: `powerbi-mcp-test-authentication` - Validates auth flow
- Skill: `powerbi-mcp-test-workspace-ops` - Tests workspace listing/querying
- Skill: `powerbi-mcp-test-semantic-model` - Tests model upload/download
- Skill: `powerbi-mcp-test-report-rebind` - Tests report upload with rebinding

**Rationale:**
- Skills can be invoked through Copilot to validate functionality
- Real API calls ensure no mocking gaps
- Test workspace isolates experiments from production
- Skills documentation serves as usage examples

## Risks / Trade-offs

**[Risk] Rate Limiting**  
→ **Mitigation:** Reuse existing `_request_with_retry()` with exponential backoff. Document rate limits in tool descriptions.

**[Risk] Authentication Token Expiration**  
→ **Mitigation:** Implement token refresh logic. Provide clear error messages when re-authentication required. Cache tokens securely.

**[Risk] Large File Downloads**  
→ **Mitigation:** Implement streaming for large .pbix files. Add progress indicators. Set reasonable timeouts.

**[Risk] Semantic Model Rebinding Complexity**  
→ **Mitigation:** Start with simple name-based matching. Document limitations. Allow users to skip rebinding and handle manually.

**[Risk] MCP Protocol Version Changes**  
→ **Mitigation:** Pin MCP SDK version. Test against stable MCP clients. Version the server clearly.

**[Trade-off] Python vs TypeScript**  
- Chose Python for code reuse, but many MCP servers are TypeScript
- Python MCP ecosystem less mature
- Accepted because value of code reuse outweighs ecosystem concerns

**[Trade-off] Granular vs Combined Tools**  
- More tools = better composability but more complex discovery
- Accepted: MCP clients handle tool discovery well, granularity helps

## Migration Plan

N/A - This is a new server, not replacing existing functionality. Deployment is:
1. Install MCP server package
2. Configure in MCP client settings (e.g., Copilot config)
3. Invoke authentication tool on first use
4. Server ready for operations

No# 8. Versioning and Metadata Strategy
**Decision:** Use DuckDB for metadata tracking with automatic versioning for downloads outside Git repositories

**Rationale:**
- DuckDB is lightweight, embedded, and requires no separate server
- Automatic versioning prevents accidental overwrites during iterative development
- Git detection allows seamless integration with existing version control workflows
- Metadata tracking enables deployment history and workspace mapping

**Implementation:**
- Detect if current directory is under Git control
- If not under Git: append timestamp/version suffix to downloaded files
- Store metadata in local DuckDB database: workspace mappings, download history, deployment records
- Track: artifact name, type, workspace, download date, file path, version, user

**Alternatives Considered:**
- JSON files for metadata: Less queryable, harder to maintain consistency
- SQLite: Similar but DuckDB better for analytical queries on deployment history
- Always version: Clutters Git repos, users prefer clean filenames in version control

**Configuration Options:**
- `versioning.enabled`: Override auto-detection (force on/off)
- `versioning.format`: Timestamp format for version suffixes
- `metadata.db_path`: Location of DuckDB database file

## Open Questions

- What level of semantic model detail should be exposed (full TMSL/TOM access)?
- Should we support dataset refresh operations, or focus purely on definition management?
- What's the preferred error handling strategy - surface full API errors or simplify for MCP clients?
- Should versioning metadata track relationships between reports and semantic models?

**Resolution Path:** Start with minimal implementation (asset download/upload + versioning), gather feedback, extend based on real usage patterns. Git integration and Fabric item support deferred to post-MVP

**Resolution Path:** Start with minimal implementation (asset download/upload only), gather feedback, extend based on real usage patterns.
