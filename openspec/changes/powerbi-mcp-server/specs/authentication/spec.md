## ADDED Requirements

### Requirement: Device Flow Authentication
The system SHALL implement Device Flow authentication to obtain Power BI API access tokens following Microsoft's recommended approach for CLI and headless tools.

#### Scenario: First-time authentication
- **WHEN** user invokes the authentication tool without cached credentials
- **THEN** system initiates Device Flow and displays user code and authentication URL
- **AND** user completes authentication in browser
- **AND** system obtains and caches valid access token

#### Scenario: Token refresh from cache
- **WHEN** user invokes authentication tool with valid cached token
- **THEN** system retrieves token from cache without requiring user interaction

#### Scenario: Expired token handling
- **WHEN** cached token is expired
- **THEN** system attempts silent token refresh
- **AND** falls back to Device Flow if refresh fails

### Requirement: Token Security
The system SHALL store authentication tokens securely using platform-appropriate encryption mechanisms.

#### Scenario: Windows DPAPI encryption
- **WHEN** running on Windows
- **THEN** system uses DPAPI (Data Protection API) to encrypt stored tokens

#### Scenario: Secure token retrieval
- **WHEN** retrieving cached tokens
- **THEN** system decrypts tokens only in memory and never logs token values

### Requirement: Multi-scope Token Support
The system SHALL obtain tokens for both Power BI API and OneLake operations in a single authentication flow.

#### Scenario: Dual scope acquisition
- **WHEN** authentication completes
- **THEN** system obtains token for Power BI API scope (https://analysis.windows.net/powerbi/api/.default)
- **AND** creates OneLake credential for Fabric operations

### Requirement: User Identity Display
The system SHALL display authenticated user information after successful authentication.

#### Scenario: User info display
- **WHEN** authentication succeeds
- **THEN** system displays user's name and email address
- **AND** confirms successful authentication with success indicator
