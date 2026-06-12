## ADDED Requirements

### Requirement: Git Detection
The system SHALL detect whether the current working directory is under Git version control.

#### Scenario: Git repository detected
- **WHEN** system checks for Git control
- **AND** current directory is within a Git repository
- **THEN** system disables automatic versioning
- **AND** downloads use clean filenames without version suffixes

#### Scenario: No Git repository detected
- **WHEN** system checks for Git control
- **AND** current directory is not under Git control
- **THEN** system enables automatic versioning
- **AND** downloads include timestamp version suffixes

#### Scenario: Manual versioning override
- **WHEN** user configures `versioning.enabled` setting explicitly
- **THEN** system respects configuration regardless of Git detection

### Requirement: Automatic File Versioning
The system SHALL automatically version downloaded files when not under Git control to prevent overwrites.

#### Scenario: First download of asset
- **WHEN** asset downloaded for first time outside Git repository
- **THEN** system saves with timestamp suffix (e.g., `model_20260513_143022.pbix`)
- **AND** records download in metadata database

#### Scenario: Subsequent download of same asset
- **WHEN** same asset downloaded again outside Git repository
- **THEN** system creates new file with current timestamp
- **AND** preserves previous versions
- **AND** updates metadata with new version entry

#### Scenario: Configurable version format
- **WHEN** user configures `versioning.format` setting
- **THEN** system applies specified timestamp format to version suffixes
- **AND** validates format before use

### Requirement: Metadata Database Management
The system SHALL maintain a DuckDB database for tracking deployment metadata and version history.

#### Scenario: Database initialization
- **WHEN** MCP server starts and no metadata database exists
- **THEN** system creates DuckDB database at configured path
- **AND** initializes schema with required tables
- **AND** creates indexes for efficient querying

#### Scenario: Metadata recording on download
- **WHEN** asset downloaded successfully
- **THEN** system records metadata entry with:
  - Artifact name and type (semantic model or report)
  - Source workspace ID and name
  - Download timestamp
  - Local file path
  - Version identifier
  - Authenticated user identity

#### Scenario: Metadata recording on upload
- **WHEN** asset uploaded successfully
- **THEN** system records deployment entry with:
  - Artifact name and type
  - Target workspace ID and name
  - Upload timestamp
  - Source file path
  - Asset ID in workspace
  - Authenticated user identity

### Requirement: Version History Queries
The system SHALL provide queryable version history for tracked assets.

#### Scenario: Query asset history
- **WHEN** user queries history for specific asset
- **THEN** system retrieves all versions from metadata database
- **AND** returns chronological list with download dates and file paths
- **AND** includes workspace source information

#### Scenario: Query workspace deployments
- **WHEN** user queries deployments to specific workspace
- **THEN** system retrieves all uploads to that workspace
- **AND** returns list with asset names, types, and timestamps
- **AND** includes local file paths used for deployment

#### Scenario: Query by date range
- **WHEN** user queries metadata with date range filter
- **THEN** system returns matching downloads and uploads within specified period

### Requirement: Workspace Mapping Tracking
The system SHALL track relationships between local files and workspace locations.

#### Scenario: Record file-to-workspace mapping
- **WHEN** asset uploaded to workspace
- **THEN** system records mapping between local file and workspace asset ID
- **AND** stores workspace name and asset name for reference

#### Scenario: Query current workspace location
- **WHEN** user queries where local file is deployed
- **THEN** system returns list of workspaces containing that asset
- **AND** includes deployment timestamps
- **AND** indicates if local file has been modified since deployment

### Requirement: Database Configuration
The system SHALL support configuration of metadata database location and settings.

#### Scenario: Default database location
- **WHEN** no database path configured
- **THEN** system uses `.powerbi-mcp-deployment/metadata.duckdb` in current directory

#### Scenario: Custom database location
- **WHEN** user configures `metadata.db_path` setting
- **THEN** system uses specified path for metadata database
- **AND** creates parent directories if needed

#### Scenario: Database migration
- **WHEN** metadata database schema version is outdated
- **THEN** system automatically migrates to current schema
- **AND** preserves existing metadata during migration

### Requirement: Metadata Cleanup
The system SHALL provide utilities for managing metadata database size and obsolete entries.

#### Scenario: Remove orphaned entries
- **WHEN** local files no longer exist
- **THEN** system can identify orphaned metadata entries
- **AND** allows user to clean up orphaned records

#### Scenario: Archive old history
- **WHEN** metadata database grows large
- **THEN** system provides option to archive entries older than specified date
- **AND** maintains recent history for active development

### Requirement: Report-to-Model Relationship Tracking
The system SHALL optionally track relationships between reports and semantic models in metadata.

#### Scenario: Record rebinding relationship
- **WHEN** report uploaded with rebinding to semantic model
- **THEN** system records relationship in metadata
- **AND** stores both report and semantic model identifiers
- **AND** includes workspace context

#### Scenario: Query report dependencies
- **WHEN** user queries which semantic model a report uses
- **THEN** system retrieves relationship from metadata
- **AND** returns semantic model name and workspace location
