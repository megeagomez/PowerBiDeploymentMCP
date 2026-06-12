# Metadata Database Backup and Migration

This document describes procedures for backing up and migrating the Power BI MCP metadata database.

## Database Location

Default location: `~/.powerbi-mcp-deployment/metadata.duckdb`

Environment variable: `POWERBI_MCP_DB_PATH`

## Backup Procedures

### Manual Backup

**Windows PowerShell:**
```powershell
# Create backup directory
$backupDir = "$env:USERPROFILE\.powerbi-mcp-deployment\backups"
New-Item -ItemType Directory -Force -Path $backupDir

# Create timestamped backup
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dbPath = "$env:USERPROFILE\.powerbi-mcp-deployment\metadata.duckdb"
$backupPath = "$backupDir\metadata_$timestamp.duckdb"

Copy-Item $dbPath $backupPath
Write-Host "Backup created: $backupPath"
```

**Unix/Linux/macOS:**
```bash
# Create backup directory
mkdir -p ~/.powerbi-mcp-deployment/backups

# Create timestamped backup
timestamp=$(date +%Y%m%d_%H%M%S)
cp ~/.powerbi-mcp-deployment/metadata.duckdb ~/.powerbi-mcp-deployment/backups/metadata_$timestamp.duckdb
echo "Backup created: ~/.powerbi-mcp-deployment/backups/metadata_$timestamp.duckdb"
```

### Automated Backup Script

**Windows (backup.ps1):**
```powershell
param(
    [int]$RetainDays = 30
)

$backupDir = "$env:USERPROFILE\.powerbi-mcp-deployment\backups"
$dbPath = "$env:USERPROFILE\.powerbi-mcp-deployment\metadata.duckdb"

# Create backup
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$backupDir\metadata_$timestamp.duckdb"
Copy-Item $dbPath $backupPath

# Remove old backups
$cutoffDate = (Get-Date).AddDays(-$RetainDays)
Get-ChildItem $backupDir -Filter "metadata_*.duckdb" |
    Where-Object { $_.LastWriteTime -lt $cutoffDate } |
    Remove-Item -Force

Write-Host "Backup completed. Old backups (>$RetainDays days) removed."
```

**Run regularly with Task Scheduler:**
```powershell
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-File C:\path\to\backup.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At "2:00 AM"
Register-ScheduledTask -TaskName "PowerBI-MCP-Backup" `
    -Action $action -Trigger $trigger
```

## Restore Procedures

### Restore from Backup

**Windows PowerShell:**
```powershell
# Stop the MCP server first!

$backupPath = "$env:USERPROFILE\.powerbi-mcp-deployment\backups\metadata_20240115_140000.duckdb"
$dbPath = "$env:USERPROFILE\.powerbi-mcp-deployment\metadata.duckdb"

# Backup current database before restore
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item $dbPath "$env:USERPROFILE\.powerbi-mcp-deployment\backups\pre_restore_$timestamp.duckdb"

# Restore from backup
Copy-Item $backupPath $dbPath -Force
Write-Host "Database restored from: $backupPath"
```

**Unix/Linux/macOS:**
```bash
# Stop the MCP server first!

backup_file=~/.powerbi-mcp-deployment/backups/metadata_20240115_140000.duckdb
db_path=~/.powerbi-mcp-deployment/metadata.duckdb

# Backup current database before restore
timestamp=$(date +%Y%m%d_%H%M%S)
cp $db_path ~/.powerbi-mcp-deployment/backups/pre_restore_$timestamp.duckdb

# Restore from backup
cp $backup_file $db_path
echo "Database restored from: $backup_file"
```

### Verify Restored Database

```python
import duckdb

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

# Check schema version
version = conn.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1").fetchone()
print(f"Schema version: {version[0]}")

# Count records
downloads = conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
uploads = conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
mappings = conn.execute("SELECT COUNT(*) FROM workspace_mappings").fetchone()[0]

print(f"Downloads: {downloads}")
print(f"Uploads: {uploads}")
print(f"Mappings: {mappings}")

conn.close()
```

## Migration Procedures

### Migrate to New Machine

**Steps:**

1. **On source machine - Export data:**
```powershell
# Backup database
$dbPath = "$env:USERPROFILE\.powerbi-mcp-deployment\metadata.duckdb"
Copy-Item $dbPath "$env:USERPROFILE\Desktop\metadata_export.duckdb"

# Export configuration (if any)
Copy-Item "$env:USERPROFILE\.powerbi-mcp-deployment\config.json" "$env:USERPROFILE\Desktop\config_export.json"
```

2. **Transfer files to new machine:**
- Use network share, USB drive, or cloud storage
- Transfer `metadata_export.duckdb` and `config_export.json`

3. **On target machine - Import data:**
```powershell
# Create directory
$mcpDir = "$env:USERPROFILE\.powerbi-mcp-deployment"
New-Item -ItemType Directory -Force -Path $mcpDir

# Copy database
Copy-Item "path\to\metadata_export.duckdb" "$mcpDir\metadata.duckdb"

# Copy configuration
Copy-Item "path\to\config_export.json" "$mcpDir\config.json"

# Clear token cache (tokens are machine-specific due to DPAPI)
Remove-Item "$mcpDir\cache\tokens.encrypted" -ErrorAction SilentlyContinue
```

4. **Re-authenticate:**
Start the server and authenticate when prompted.

### Migrate Between Environments (Dev/Prod)

**Scenario:** Move metadata from development to production

1. **Export specific data:**
```python
import duckdb

source_conn = duckdb.connect('~/.powerbi-mcp-deployment/dev-metadata.duckdb')
target_conn = duckdb.connect('~/.powerbi-mcp-deployment/prod-metadata.duckdb')

# Export workspace mappings only (skip download/upload history)
mappings = source_conn.execute("""
    SELECT * FROM workspace_mappings
    WHERE workspace_name LIKE 'PROD%'
""").fetchdf()

# Import to target
target_conn.execute("DELETE FROM workspace_mappings")
target_conn.execute("INSERT INTO workspace_mappings SELECT * FROM mappings")

source_conn.close()
target_conn.close()
```

### Schema Migration (Version Upgrade)

When upgrading to a new server version with schema changes:

1. **Backup current database**

2. **Check schema version:**
```python
import duckdb

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')
current_version = conn.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1").fetchone()[0]
print(f"Current schema version: {current_version}")
conn.close()
```

3. **Apply migration scripts:**

Server automatically applies migrations on startup if needed. To manually apply:

```python
from powerbi_mcp_server.metadata import MetadataDatabase

db = MetadataDatabase()
db.connect()
db.initialize_schema()  # Applies migrations
db.close()
```

4. **Verify migration:**
Check logs for migration messages and verify data integrity.

## Export Data for Analysis

### Export to CSV

```python
import duckdb
import csv

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

# Export downloads history
downloads = conn.execute("""
    SELECT 
        artifact_name,
        artifact_type,
        workspace_name,
        download_timestamp,
        local_file_path,
        version_suffix
    FROM downloads
    ORDER BY download_timestamp DESC
""").fetchdf()

downloads.to_csv('downloads_export.csv', index=False)

# Export workspace mappings
mappings = conn.execute("SELECT * FROM workspace_mappings").fetchdf()
mappings.to_csv('mappings_export.csv', index=False)

conn.close()
print("Data exported to CSV files")
```

### Export to JSON

```python
import duckdb
import json

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

# Export all data
data = {
    'downloads': conn.execute("SELECT * FROM downloads").fetchdf().to_dict(orient='records'),
    'uploads': conn.execute("SELECT * FROM uploads").fetchdf().to_dict(orient='records'),
    'mappings': conn.execute("SELECT * FROM workspace_mappings").fetchdf().to_dict(orient='records'),
    'relationships': conn.execute("SELECT * FROM report_model_relationships").fetchdf().to_dict(orient='records')
}

with open('metadata_export.json', 'w') as f:
    json.dump(data, f, indent=2, default=str)

conn.close()
print("Data exported to metadata_export.json")
```

## Database Maintenance

### Compact Database

DuckDB automatically manages space, but you can manually compact:

```python
import duckdb

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')
conn.execute("CHECKPOINT")
conn.execute("VACUUM")
conn.close()
```

### Clean Old Entries

```python
import duckdb
from datetime import datetime, timedelta

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

# Remove downloads older than 90 days
cutoff_date = datetime.now() - timedelta(days=90)
deleted = conn.execute("""
    DELETE FROM downloads
    WHERE download_timestamp < ?
""", [cutoff_date]).fetchone()[0]

print(f"Removed {deleted} old download records")

# Remove orphaned mappings
from powerbi_mcp_server.metadata import MetadataManager

manager = MetadataManager()
orphaned = manager.cleanup_orphaned_entries()
print(f"Removed {orphaned} orphaned mapping entries")

conn.close()
```

### Check Database Integrity

```python
import duckdb

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

# Pragma integrity check
result = conn.execute("PRAGMA integrity_check").fetchall()
if result[0][0] == 'ok':
    print("Database integrity: OK")
else:
    print(f"Database integrity issues: {result}")

conn.close()
```

## Disaster Recovery

### Complete Data Loss

If database is lost and no backup exists:

1. **Recreate database:**
Server will automatically create new database on startup.

2. **Re-establish mappings:**
Manually re-upload artifacts to recreate workspace mappings.

3. **History is lost:**
Download/upload history cannot be recovered.

### Corrupted Database

If database is corrupted:

1. **Try automatic repair:**
```python
import duckdb

try:
    conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')
    conn.execute("PRAGMA force_checkpoint")
    conn.close()
    print("Repair attempt completed")
except Exception as e:
    print(f"Automatic repair failed: {e}")
```

2. **Export recoverable data:**
```python
import duckdb

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

try:
    # Try to export what's accessible
    mappings = conn.execute("SELECT * FROM workspace_mappings").fetchdf()
    mappings.to_csv('recovered_mappings.csv', index=False)
    print("Recovered mappings saved")
except Exception as e:
    print(f"Failed to recover: {e}")

conn.close()
```

3. **Recreate database:**
```powershell
Remove-Item ~\.powerbi-mcp-deployment\metadata.duckdb -Force
# Restart server to recreate
```

4. **Import recovered data:**
```python
import duckdb
import pandas as pd

conn = duckdb.connect('~/.powerbi-mcp-deployment/metadata.duckdb')

# Import recovered mappings
mappings = pd.read_csv('recovered_mappings.csv')
conn.execute("DELETE FROM workspace_mappings")
conn.execute("INSERT INTO workspace_mappings SELECT * FROM mappings")

conn.close()
```
