## ADDED Requirements

### Requirement: VS Code Skills for Testing
The system SHALL include VS Code skills that validate all MCP operations against real Power BI workspaces.

#### Scenario: Skill invocation
- **WHEN** developer invokes test skill through GitHub Copilot
- **THEN** system executes corresponding test workflow
- **AND** reports results with pass/fail status

#### Scenario: Test isolation
- **WHEN** test skills execute
- **THEN** system uses dedicated test workspace
- **AND** does not affect production workspaces
- **AND** cleans up test artifacts after execution

### Requirement: Authentication Testing Skill
The system SHALL provide a skill that validates Device Flow authentication.

#### Scenario: Authentication skill execution
- **WHEN** powerbi-mcp-test-authentication skill invoked
- **THEN** system attempts Device Flow authentication
- **AND** verifies token acquisition
- **AND** validates token scopes
- **AND** confirms secure token storage
- **AND** reports authentication success/failure

### Requirement: Workspace Operations Testing Skill
The system SHALL provide a skill that validates workspace listing and querying.

#### Scenario: Workspace operations skill execution
- **WHEN** powerbi-mcp-test-workspace-ops skill invoked
- **THEN** system lists all accessible workspaces
- **AND** queries test workspace contents
- **AND** searches for specific workspace by name
- **AND** validates all returned data structures
- **AND** reports success/failure for each operation

### Requirement: Semantic Model Testing Skill
The system SHALL provide a skill that validates semantic model upload and download operations.

#### Scenario: Semantic model skill execution
- **WHEN** powerbi-mcp-test-semantic-model skill invoked
- **THEN** system uploads test semantic model to test workspace
- **AND** verifies upload success
- **AND** downloads same semantic model
- **AND** validates downloaded content matches original
- **AND** cleans up test semantic model
- **AND** reports operation results

### Requirement: Report Rebinding Testing Skill
The system SHALL provide a skill that validates report upload with semantic model rebinding.

#### Scenario: Report rebinding skill execution
- **WHEN** powerbi-mcp-test-report-rebind skill invoked
- **THEN** system uploads test semantic model to test workspace
- **AND** uploads test report with different original model reference
- **AND** triggers rebinding prompt
- **AND** simulates user selecting rebind to uploaded semantic model
- **AND** verifies report connects to correct semantic model
- **AND** cleans up test artifacts
- **AND** reports rebinding test results

### Requirement: Test Artifacts Management
The system SHALL manage test artifacts lifecycle during skill execution.

#### Scenario: Pre-test setup
- **WHEN** test skill begins execution
- **THEN** system prepares required test files
- **AND** validates test workspace accessibility
- **AND** confirms no conflicting artifacts exist

#### Scenario: Post-test cleanup
- **WHEN** test skill completes (success or failure)
- **THEN** system removes created test artifacts from workspace
- **AND** deletes temporary local files
- **AND** restores test workspace to clean state

### Requirement: Test Result Reporting
The system SHALL provide detailed test execution reports.

#### Scenario: Successful test execution
- **WHEN** all test operations succeed
- **THEN** system reports overall success
- **AND** includes execution time for each operation
- **AND** logs all operation details

#### Scenario: Failed test execution
- **WHEN** any test operation fails
- **THEN** system reports failure with specific error
- **AND** includes context about failure point
- **AND** provides diagnostic information
- **AND** continues with cleanup despite failure

### Requirement: Test Workspace Configuration
The system SHALL allow configuration of test workspace through skill parameters.

#### Scenario: Default test workspace
- **WHEN** test skill invoked without workspace specification
- **THEN** system uses default configured test workspace

#### Scenario: Custom test workspace
- **WHEN** test skill invoked with specific workspace parameter
- **THEN** system executes tests against specified workspace
- **AND** validates workspace exists and is accessible
