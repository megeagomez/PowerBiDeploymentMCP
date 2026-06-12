## ADDED Requirements

### Requirement: Download Report
The system SHALL enable downloading Power BI reports from workspaces to local storage supporting all format variations.

#### Scenario: Download PBIR format (Power BI Report - folder structure)
- **WHEN** user requests to download a report in PBIR format
- **THEN** system uses Fabric Items API getDefinition endpoint
- **AND** retrieves all definition parts (report.json, definition.pbir, item.metadata.json, etc.)
- **AND** creates directory structure with all PBIR artifacts
- **AND** preserves original semantic model connection information
- **AND** applies versioning if not under Git control

#### Scenario: Download legacy JSON format (single file)
- **WHEN** user requests to download report in legacy JSON format
- **THEN** system uses appropriate API to export report definition
- **AND** saves as single JSON file containing complete report definition
- **AND** preserves semantic model binding information

#### Scenario: Auto-detect report format from source
- **WHEN** user does not specify format explicitly
- **THEN** system detects report's native format (PBIR vs legacy)
- **AND** downloads in original format maintaining fidelity

#### Scenario: Report not found
- **WHEN** requested report doesn't exist in workspace
- **THEN** system returns clear error indicating report not found

### Requirement: Upload Report
The system SHALL enable uploading Power BI reports from local storage to workspaces supporting all format variations.

#### Scenario: Upload PBIR directory (Power BI Report - folder structure)
- **WHEN** user uploads Power BI Report directory
- **THEN** system creates item using Fabric Items API
- **AND** uses updateDefinition endpoint with format "PowerBIReport"
- **AND** packages all parts (report.json, definition.pbir, etc.) as Base64 payloads
- **AND** preserves or rebinds semantic model connection as configured
- **AND** returns report ID and name

#### Scenario: Upload legacy JSON format (single file)
- **WHEN** user uploads legacy JSON report file
- **THEN** system uses appropriate API for legacy report import
- **AND** creates report from JSON definition
- **AND** handles semantic model binding according to rebinding settings

#### Scenario: Upload report without rebinding
- **WHEN** user uploads report and declines rebinding
- **THEN** system imports report with original semantic model connection reference
- **AND** creates report in target workspace
- **AND** returns report ID and name
- **AND** warns if original semantic model not found in target workspace

#### Scenario: Upload report to workspace with original model
- **WHEN** user uploads report to workspace containing the original semantic model
- **THEN** system automatically connects to original model by ID or name
- **AND** completes upload without prompting for rebinding

### Requirement: Interactive Semantic Model Rebinding
The system SHALL offer interactive rebinding of reports to different semantic models during upload.

#### Scenario: Rebind with matching models found
- **WHEN** user uploads report to workspace without original semantic model
- **AND** workspace contains semantic models with similar names
- **THEN** system presents list of available semantic models
- **AND** prompts user to select target model
- **AND** rebinds report to selected model upon confirmation

#### Scenario: Rebind with no matching models
- **WHEN** user uploads report to workspace without original semantic model
- **AND** no semantic models exist in target workspace
- **THEN** system warns user about missing semantic model
- **AND** offers to upload with original connection (will fail at runtime)
- **OR** cancel upload operation

#### Scenario: User skips rebinding
- **WHEN** system offers rebinding options
- **AND** user explicitly skips rebinding
- **THEN** system proceeds with original semantic model connection
- **AND** logs warning about potential connection issues

### Requirement: Semantic Model Name Matching
The system SHALL use intelligent name matching to suggest rebinding candidates.

#### Scenario: Exact name match
- **WHEN** target workspace contains semantic model with exact name match
- **THEN** system prioritizes exact match as top rebinding suggestion

#### Scenario: Partial name match
- **WHEN** no exact match exists
- **AND** workspace contains models with partial name similarity
- **THEN** system ranks suggestions by name similarity
- **AND** displays all candidates for user selection

### Requirement: Report Validation
The system SHALL validate report compatibility before upload.

#### Scenario: Valid report format
- **WHEN** user attempts to upload report file
- **THEN** system validates file format is valid PBIR
- **AND** proceeds with upload if valid

#### Scenario: Invalid report format
- **WHEN** uploaded file is not valid report format
- **THEN** system returns error indicating format issue
- **AND** suggests correct format requirements
