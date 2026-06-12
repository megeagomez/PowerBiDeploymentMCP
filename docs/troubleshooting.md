# Troubleshooting Guide

Common issues and solutions for the Power BI MCP server.

## Authentication Issues

### Token Expired or Invalid

**Symptoms:**
- Error: "Error de autenticación. El token ha expirado o es inválido."
- HTTP 401 errors

**Solutions:**

1. **Clear cached tokens and re-authenticate:**
```powershell
Remove-Item ~\.powerbi-mcp-deployment\cache\tokens.encrypted -Force
```

2. **Check token expiration:**
Tokens expire after 1 hour. The server automatically refreshes them, but if the refresh fails, manual re-authentication is needed.

3. **Verify Azure AD configuration:**
- Ensure you have access to the Azure AD tenant
- Verify the application ID is correct (default: `04b07795-8ddb-461a-bbee-02f9e1bf7b46`)

### Device Flow Not Working

**Symptoms:**
- Device code prompt doesn't appear
- Browser doesn't open

**Solutions:**

1. **Manual browser navigation:**
Copy the device code URL manually and paste in browser:
```
https://microsoft.com/devicelogin
```

2. **Check firewall/proxy:**
Ensure outbound HTTPS connections to `login.microsoftonline.com` are allowed.

3. **Verify network connectivity:**
```powershell
Test-NetConnection login.microsoftonline.com -Port 443
```

## Rate Limiting

### HTTP 429 Errors

**Symptoms:**
- Error: "Rate limit alcanzado (429)"
- Frequent retries

**Solutions:**

1. **Wait for automatic retry:**
The server uses exponential backoff (2^attempt seconds). Wait for automatic completion.

2. **Reduce concurrent operations:**
Avoid multiple simultaneous uploads/downloads.

3. **Check rate limit status:**
Power BI API has limits:
- 200 requests per hour per user
- 1200 requests per hour per capacity

4. **Use batch operations:**
Group multiple operations when possible.

## Workspace Issues

### Workspace Not Found

**Symptoms:**
- Error: "Workspace no encontrado: {name}"

**Solutions:**

1. **Verify exact name (case-sensitive):**
```json
{
  "workspace_name": "My Workspace"  // Exact match required
}
```

2. **List all accessible workspaces:**
```json
{
  "tool": "list_workspaces",
  "arguments": {}
}
```

3. **Check permissions:**
- Ensure you have at least Viewer role
- Verify workspace is not archived
- Check workspace hasn't been deleted

4. **Use OData filter:**
```json
{
  "filter": "contains(name, 'Sales')"
}
```

### Access Denied (403)

**Symptoms:**
- Error: "Acceso denegado. No tienes permisos suficientes para esta operación."

**Solutions:**

1. **Check workspace role:**
- Download requires: Viewer or higher
- Upload requires: Contributor or higher

2. **Verify capacity assignment:**
Workspace must be assigned to a capacity you have access to.

3. **Check organizational policies:**
Some organizations restrict API access.

## File Format Issues

### Format Not Detected

**Symptoms:**
- Error: "No se pudo detectar el formato del modelo semántico"

**Solutions:**

1. **Specify format explicitly:**
```json
{
  "format": "pbix"  // or "pbip", "pbir", "json"
}
```

2. **Verify file structure:**

**PBIX:**
- Must be `.pbix` file
- Must exist and be readable

**PBIP:**
- Must be directory
- Must contain `item.metadata.json` or `model.bim`

**PBIR:**
- Must be directory
- Must contain `definition.pbir` or `report.json`

3. **Check file permissions:**
```powershell
Get-Acl C:\path\to\file.pbix | Format-List
```

### PBIP/PBIR Upload Fails

**Symptoms:**
- Error during upload of folder-based formats
- Missing parts in uploaded item

**Solutions:**

1. **Verify folder structure:**
```
semantic-model/
├── item.metadata.json
├── model.bim
└── .pbi/
    └── ...
```

2. **Check file encoding:**
PBIP/PBIR files must be UTF-8 encoded.

3. **Validate JSON structure:**
```powershell
Get-Content definition.pbir | ConvertFrom-Json
```

## Versioning Issues

### Versioning Not Working

**Symptoms:**
- Files downloaded without version suffix
- Expected versioning not applied

**Solutions:**

1. **Check Git detection:**
```powershell
git rev-parse --is-inside-work-tree
# Should return 'true' if in Git repo
```

2. **Force enable versioning:**
```json
{
  "env": {
    "POWERBI_MCP_VERSIONING_ENABLED": "true"
  }
}
```

3. **Verify target directory:**
Versioning applies to directory where file is saved, not current working directory.

4. **Check Git installation:**
```powershell
git --version
```

### Incorrect Version Format

**Symptoms:**
- Version suffix format not as expected

**Solutions:**

1. **Set custom format:**
```json
{
  "env": {
    "POWERBI_MCP_VERSION_FORMAT": "%Y%m%d_%H%M%S"
  }
}
```

2. **Format examples:**
- `%Y%m%d_%H%M%S`: `20240115_143045`
- `%Y-%m-%d`: `2024-01-15`
- `%Y%m%d-%H%M`: `20240115-1430`

## Metadata Database Issues

### Database Locked

**Symptoms:**
- Error: "database is locked"

**Solutions:**

1. **Close other connections:**
Ensure only one server instance is running.

2. **Delete lock file:**
```powershell
Remove-Item ~\.powerbi-mcp-deployment\metadata.duckdb.wal -Force
```

3. **Restart server:**
Kill all `powerbi-mcp-deployment` processes and restart.

### Orphaned Entries

**Symptoms:**
- Metadata references non-existent files

**Solutions:**

1. **Run cleanup:**
```json
{
  "tool": "cleanup_metadata",
  "arguments": {}
}
```

2. **Manual cleanup:**
```sql
DELETE FROM workspace_mappings
WHERE local_file_path NOT IN (
  SELECT path FROM existing_files
);
```

### Database Corruption

**Symptoms:**
- Error: "database disk image is malformed"

**Solutions:**

1. **Backup and recreate:**
```powershell
Copy-Item ~\.powerbi-mcp-deployment\metadata.duckdb ~\.powerbi-mcp-deployment\metadata.backup.duckdb
Remove-Item ~\.powerbi-mcp-deployment\metadata.duckdb -Force
# Restart server to recreate schema
```

2. **Restore from backup:**
```powershell
Copy-Item ~\.powerbi-mcp-deployment\metadata.backup.duckdb ~\.powerbi-mcp-deployment\metadata.duckdb -Force
```

## Network Issues

### Connection Timeouts

**Symptoms:**
- Error: "Connection timeout"
- Long waits during API calls

**Solutions:**

1. **Check internet connection:**
```powershell
Test-NetConnection api.powerbi.com -Port 443
Test-NetConnection api.fabric.microsoft.com -Port 443
```

2. **Verify proxy settings:**
```powershell
$env:HTTP_PROXY
$env:HTTPS_PROXY
```

3. **Increase timeout (if supported):**
Check client configuration for timeout settings.

### SSL Certificate Errors

**Symptoms:**
- Error: "SSL certificate verify failed"

**Solutions:**

1. **Update root certificates:**
```powershell
Update-MpSignature
```

2. **Check corporate proxy:**
Corporate proxies may intercept SSL. Contact IT department.

3. **Temporary workaround (not recommended for production):**
Set environment variable (development only):
```bash
PYTHONHTTPSVERIFY=0
```

## Performance Issues

### Slow Downloads/Uploads

**Symptoms:**
- Operations take very long to complete
- Progress appears stuck

**Solutions:**

1. **Check file size:**
Large PBIX files (>100MB) can take several minutes.

2. **Verify network bandwidth:**
```powershell
Test-NetSpeed
```

3. **Use PBIP instead of PBIX:**
PBIP format is more efficient for large models.

4. **Check disk I/O:**
Slow local disk can bottleneck operations.

### High Memory Usage

**Symptoms:**
- Server process consuming excessive memory

**Solutions:**

1. **Restart server:**
Memory leaks should be reported as bugs.

2. **Reduce concurrent operations:**
Process items sequentially instead of in parallel.

3. **Check DuckDB cache:**
Large metadata database may use significant memory.

## Logging and Diagnostics

### Enable Debug Logging

```json
{
  "env": {
    "POWERBI_MCP_LOG_LEVEL": "DEBUG"
  }
}
```

### Log Locations

- Server logs: `~/.powerbi-mcp-deployment/logs/powerbi_mcp_deployment.log`
- Authentication logs: Check `auth.log`
- API logs: Check `api.log`

### View Recent Logs

```powershell
Get-Content ~\.powerbi-mcp-deployment\logs\powerbi_mcp_deployment.log -Tail 50
```

### Search Logs for Errors

```powershell
Select-String -Path ~\.powerbi-mcp-deployment\logs\*.log -Pattern "ERROR"
```

## Getting Help

If issues persist:

1. **Check GitHub Issues:**
   https://github.com/yourorg/powerbi-mcp-deployment/issues

2. **Enable debug logging and collect logs**

3. **Provide information:**
   - Operating system and version
   - Python version
   - Power BI tenant type (personal, organizational)
   - Error messages and stack traces
   - Steps to reproduce

4. **Create minimal reproduction:**
   Simplify scenario to smallest failing case.
