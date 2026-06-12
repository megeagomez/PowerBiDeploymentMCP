## ADDED Requirements

### Requirement: Download Semantic Model
The system SHALL enable downloading semantic models from Power BI workspaces to local storage in multiple formats.

#### Scenario: Download PBIX format (legacy binary)
- **WHEN** user requests to download a semantic model specifying PBIX format
- **THEN** system uses Power BI REST API export endpoint
- **AND** downloads semantic model as single .pbix binary file
- **AND** saves file to specified local path with versioning if applicable

#### Scenario: Download PBIP format (Power BI Project)
- **WHEN** user requests to download a semantic model specifying PBIP format
- **THEN** system uses Fabric Items API getDefinition endpoint
- **AND** retrieves all definition parts (model.bim, item.metadata.json, item.config.json, etc.)
- **AND** creates directory structure with all PBIP artifacts
- **AND** saves each part to appropriate path maintaining folder structure

#### Scenario: Auto-detect format from source
- **WHEN** user does not specify format explicitly
- **THEN** system detects if semantic model was created from PBIX or PBIP
- **AND** downloads in native format

#### Scenario: Non-existent semantic model
- **WHEN** user requests download of semantic model that doesn't exist
- **THEN** system returns clear error message indicating model not found

### Requirement: Upload Semantic Model
The system SHALL enable uploading semantic models from local storage to Power BI workspaces supporting all format variations.

#### Scenario: Upload PBIX file (legacy binary)
- **WHEN** user uploads .pbix file to a workspace
- **THEN** system uses Power BI REST API PostImportWithFile endpoint
- **AND** uploads binary file as multipart/form-data
- **AND** creates new semantic model in target workspace
- **AND** returns semantic model ID and name

#### Scenario: Upload PBIP directory (Power BI Project)
- **WHEN** user uploads Power BI Project directory
- **THEN** system creates item using Fabric Items API
- **AND** uses updateDefinition endpoint with format "PowerBIProject"
- **AND** packages all parts (model.bim, definitions, etc.) as Base64 payloads
- **AND** creates semantic model with proper metadata structure

#### Scenario: Upload PBIP with dependencies
- **WHEN** PBIP contains external dependencies or connections
- **THEN** system validates dependencies exist in target workspace
- **AND** prompts user to resolve missing dependencies
- **AND** proceeds with upload after confirmation

#### Scenario: Overwrite existing model
- **WHEN** user uploads semantic model with name that already exists
- **THEN** system prompts user for confirmation
- **AND** uses appropriate update mechanism (updateDefinition for PBIP, re-import for PBIX)
- **OR** cancels operation if declined

### Requirement: Workspace Validation
The system SHALL validate workspace access before performing semantic model operations.

#### Scenario: Valid workspace access
- **WHEN** user attempts semantic model operation
- **THEN** system verifies user has appropriate permissions in target workspace
- **AND** proceeds with operation if authorized

#### Scenario: Insufficient permissions
- **WHEN** user lacks required permissions
- **THEN** system returns error indicating insufficient access
- **AND** specifies required permission level

### Requirement: Rate Limiting Resilience
The system SHALL handle Power BI API rate limits gracefully during semantic model operations.

#### Scenario: Rate limit encountered
- **WHEN** API returns 429 (Too Many Requests) status
- **THEN** system implements exponential backoff retry strategy
- **AND** waits progressively longer between retry attempts
- **AND** succeeds when rate limit window resets

#### Scenario: Maximum retries exceeded
- **WHEN** rate limit persists after maximum retry attempts
- **THEN** system returns error with retry suggestion
- **AND** includes estimated wait time
