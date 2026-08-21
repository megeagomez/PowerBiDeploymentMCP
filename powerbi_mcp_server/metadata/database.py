"""
DuckDB Metadata Database Schema and Operations

Manages metadata tracking for Power BI assets including version history,
workspace mappings, and report-to-model relationships.
"""

import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import duckdb

logger = logging.getLogger(__name__)

# DuckDB allows only one process to hold a given database file open at a
# time. This package can be launched as more than one independent OS process
# against the same metadata.duckdb (e.g. a normal chat session plus a
# separate "Cowork/Code" copy Claude Desktop starts for itself) — if two of
# them call connect() within the same short startup window, one gets a
# duckdb.IOException. These retries ride out that race instead of crashing.
_LOCK_RETRY_ATTEMPTS = 6
_LOCK_RETRY_BASE_DELAY = 0.25  # seconds, doubles each attempt


class MetadataDatabase:
    """
    DuckDB database for metadata tracking.
    Each public method opens and closes its own connection so the file
    is never held open between operations (avoids cross-process lock conflicts).
    """

    SCHEMA_VERSION = 5

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            env_path = os.environ.get("POWERBI_MCP_DB_PATH")
            if env_path:
                db_path = Path(env_path)
            else:
                db_path = Path.home() / ".powerbi-mcp-deployment" / "metadata.duckdb"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Metadata database path: {self.db_path}")

    @contextmanager
    def _db(self):
        """
        Open a fresh connection, yield it, then close it.

        Retries with exponential backoff if another process currently holds
        the file open (duckdb.IOException) — see module docstring above.
        """
        conn = None
        delay = _LOCK_RETRY_BASE_DELAY
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                conn = duckdb.connect(str(self.db_path))
                break
            except duckdb.IOException as e:
                if attempt == _LOCK_RETRY_ATTEMPTS - 1:
                    raise
                logger.warning(
                    f"Metadata database locked by another process "
                    f"(attempt {attempt + 1}/{_LOCK_RETRY_ATTEMPTS}), "
                    f"retrying in {delay:.2f}s: {e}"
                )
                time.sleep(delay)
                delay *= 2
        try:
            yield conn
        finally:
            conn.close()

    # Keep connect/close for any callers that relied on them (no-ops now)
    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    @staticmethod
    def _next_id(conn, table: str) -> int:
        row = conn.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}").fetchone()
        return int(row[0])

    def initialize_schema(self) -> None:
        """Create database tables if they don't exist"""
        logger.info("Initializing database schema")
        with self._db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY,
                    artifact_name VARCHAR NOT NULL,
                    artifact_type VARCHAR NOT NULL,
                    workspace_id VARCHAR NOT NULL,
                    workspace_name VARCHAR NOT NULL,
                    download_timestamp TIMESTAMP NOT NULL,
                    local_file_path VARCHAR NOT NULL,
                    version_suffix VARCHAR,
                    user_email VARCHAR,
                    file_size_bytes BIGINT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY,
                    artifact_name VARCHAR NOT NULL,
                    artifact_type VARCHAR NOT NULL,
                    workspace_id VARCHAR NOT NULL,
                    workspace_name VARCHAR NOT NULL,
                    upload_timestamp TIMESTAMP NOT NULL,
                    source_file_path VARCHAR NOT NULL,
                    asset_id VARCHAR NOT NULL,
                    user_email VARCHAR,
                    operation_type VARCHAR DEFAULT 'create'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_mappings (
                    id INTEGER PRIMARY KEY,
                    local_file_path VARCHAR NOT NULL,
                    workspace_id VARCHAR NOT NULL,
                    workspace_name VARCHAR NOT NULL,
                    asset_id VARCHAR NOT NULL,
                    asset_name VARCHAR NOT NULL,
                    asset_type VARCHAR NOT NULL,
                    last_deployed_at TIMESTAMP NOT NULL,
                    file_hash VARCHAR
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS report_model_relationships (
                    id INTEGER PRIMARY KEY,
                    report_id VARCHAR NOT NULL,
                    report_name VARCHAR NOT NULL,
                    semantic_model_id VARCHAR NOT NULL,
                    semantic_model_name VARCHAR NOT NULL,
                    workspace_id VARCHAR NOT NULL,
                    workspace_name VARCHAR NOT NULL,
                    relationship_type VARCHAR DEFAULT 'rebind',
                    created_at TIMESTAMP NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deployment_profiles (
                    id INTEGER PRIMARY KEY,
                    profile_name VARCHAR UNIQUE NOT NULL,
                    description VARCHAR,
                    target_workspace_id VARCHAR,
                    target_workspace_name VARCHAR,
                    environment_type VARCHAR DEFAULT 'development',
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_model_configs (
                    id INTEGER PRIMARY KEY,
                    model_name VARCHAR NOT NULL,
                    local_path_pattern VARCHAR,
                    target_workspace_id VARCHAR NOT NULL,
                    target_workspace_name VARCHAR NOT NULL,
                    profile_id INTEGER,
                    auto_deploy BOOLEAN DEFAULT false,
                    deploy_on_change BOOLEAN DEFAULT false,
                    notes VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (profile_id) REFERENCES deployment_profiles(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS report_configs (
                    id INTEGER PRIMARY KEY,
                    report_name VARCHAR NOT NULL,
                    local_path_pattern VARCHAR,
                    target_workspace_id VARCHAR NOT NULL,
                    target_workspace_name VARCHAR NOT NULL,
                    target_semantic_model_id VARCHAR,
                    target_semantic_model_name VARCHAR,
                    target_model_workspace_id VARCHAR,
                    target_model_workspace_name VARCHAR,
                    profile_id INTEGER,
                    auto_deploy BOOLEAN DEFAULT false,
                    auto_rebind BOOLEAN DEFAULT true,
                    notes VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (profile_id) REFERENCES deployment_profiles(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_artifact ON downloads(artifact_name, artifact_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_workspace ON downloads(workspace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_workspace ON uploads(workspace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mappings_file ON workspace_mappings(local_file_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mappings_asset ON workspace_mappings(asset_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_configs_model ON semantic_model_configs(model_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_report_configs_report ON report_configs(report_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_name ON deployment_profiles(profile_name)")

            # v3: environment hierarchy (stage_order) + projects + promotion/drift tracking
            conn.execute("ALTER TABLE deployment_profiles ADD COLUMN IF NOT EXISTS stage_order INTEGER")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    project_name VARCHAR UNIQUE NOT NULL,
                    description VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_artifacts (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    artifact_type VARCHAR NOT NULL,
                    artifact_name VARCHAR NOT NULL,
                    rebind_to_artifact_name VARCHAR,
                    sequence_order INTEGER,
                    notes VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    UNIQUE (project_id, artifact_type, artifact_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS environment_artifact_state (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    profile_id INTEGER NOT NULL,
                    artifact_type VARCHAR NOT NULL,
                    artifact_name VARCHAR NOT NULL,
                    workspace_item_id VARCHAR,
                    workspace_id VARCHAR,
                    workspace_name VARCHAR,
                    definition_hash VARCHAR,
                    source_profile_id INTEGER,
                    promotion_event_id INTEGER,
                    last_operation VARCHAR NOT NULL,
                    updated_by VARCHAR,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (profile_id) REFERENCES deployment_profiles(id),
                    UNIQUE (project_id, profile_id, artifact_type, artifact_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS promotion_events (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    operation VARCHAR NOT NULL,
                    from_profile_id INTEGER,
                    to_profile_id INTEGER NOT NULL,
                    artifact_summary VARCHAR,
                    drift_detected BOOLEAN DEFAULT false,
                    drift_confirmed BOOLEAN DEFAULT false,
                    status VARCHAR DEFAULT 'success',
                    error_message VARCHAR,
                    initiated_by VARCHAR,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (from_profile_id) REFERENCES deployment_profiles(id),
                    FOREIGN KEY (to_profile_id) REFERENCES deployment_profiles(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project_artifacts_project ON project_artifacts(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_env_state_lookup ON environment_artifact_state(project_id, profile_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_events_project ON promotion_events(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_stage_order ON deployment_profiles(stage_order)")

            # v4: per-artifact target folder path within its workspace
            conn.execute("ALTER TABLE project_artifacts ADD COLUMN IF NOT EXISTS folder_path VARCHAR")

            # v5: per-project workspace overrides (dedicated workspaces per project/environment,
            # optionally split by artifact type) — takes precedence over the environment's default
            # target_workspace when resolving where to deploy/promote a given artifact.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_environment_workspaces (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    profile_id INTEGER NOT NULL,
                    artifact_type VARCHAR,
                    workspace_id VARCHAR NOT NULL,
                    workspace_name VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (profile_id) REFERENCES deployment_profiles(id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_project_env_workspaces_lookup "
                "ON project_environment_workspaces(project_id, profile_id)"
            )

            result = conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = ?", [self.SCHEMA_VERSION]).fetchone()
            if result[0] == 0:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", [self.SCHEMA_VERSION])

        logger.info("Database schema initialized")

    def record_download(
        self,
        artifact_name: str,
        artifact_type: str,
        workspace_id: str,
        workspace_name: str,
        local_file_path: str,
        version_suffix: Optional[str] = None,
        user_email: Optional[str] = None,
        file_size_bytes: Optional[int] = None
    ) -> int:
        with self._db() as conn:
            download_id = self._next_id(conn, 'downloads')
            conn.execute("""
                INSERT INTO downloads (
                    id, artifact_name, artifact_type, workspace_id, workspace_name,
                    download_timestamp, local_file_path, version_suffix, user_email, file_size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                download_id,
                artifact_name, artifact_type, workspace_id, workspace_name,
                datetime.now(), local_file_path, version_suffix, user_email, file_size_bytes
            ])
        logger.info(f"Recorded download: {artifact_name} (ID: {download_id})")
        return download_id

    def record_upload(
        self,
        artifact_name: str,
        artifact_type: str,
        workspace_id: str,
        workspace_name: str,
        source_file_path: str,
        asset_id: str,
        user_email: Optional[str] = None,
        operation_type: str = 'create'
    ) -> int:
        with self._db() as conn:
            upload_id = self._next_id(conn, 'uploads')
            conn.execute("""
                INSERT INTO uploads (
                    id, artifact_name, artifact_type, workspace_id, workspace_name,
                    upload_timestamp, source_file_path, asset_id, user_email, operation_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                upload_id,
                artifact_name, artifact_type, workspace_id, workspace_name,
                datetime.now(), source_file_path, asset_id, user_email, operation_type
            ])
        logger.info(f"Recorded upload: {artifact_name} (ID: {upload_id})")
        return upload_id

    def upsert_workspace_mapping(
        self,
        local_file_path: str,
        workspace_id: str,
        workspace_name: str,
        asset_id: str,
        asset_name: str,
        asset_type: str,
        file_hash: Optional[str] = None
    ) -> None:
        with self._db() as conn:
            existing = conn.execute(
                "SELECT id FROM workspace_mappings WHERE local_file_path = ? AND asset_id = ?",
                [local_file_path, asset_id]
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE workspace_mappings
                    SET workspace_id = ?, workspace_name = ?, asset_name = ?,
                        last_deployed_at = ?, file_hash = ?
                    WHERE id = ?
                """, [workspace_id, workspace_name, asset_name, datetime.now(), file_hash, existing[0]])
                logger.info(f"Updated workspace mapping: {local_file_path}")
            else:
                mapping_id = self._next_id(conn, 'workspace_mappings')
                conn.execute("""
                    INSERT INTO workspace_mappings (
                        id, local_file_path, workspace_id, workspace_name, asset_id,
                        asset_name, asset_type, last_deployed_at, file_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    mapping_id,
                    local_file_path, workspace_id, workspace_name, asset_id,
                    asset_name, asset_type, datetime.now(), file_hash
                ])
                logger.info(f"Created workspace mapping: {local_file_path}")

    def record_report_model_relationship(
        self,
        report_id: str,
        report_name: str,
        semantic_model_id: str,
        semantic_model_name: str,
        workspace_id: str,
        workspace_name: str,
        relationship_type: str = 'rebind'
    ) -> int:
        with self._db() as conn:
            relationship_id = self._next_id(conn, 'report_model_relationships')
            conn.execute("""
                INSERT INTO report_model_relationships (
                    id, report_id, report_name, semantic_model_id, semantic_model_name,
                    workspace_id, workspace_name, relationship_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                relationship_id,
                report_id, report_name, semantic_model_id, semantic_model_name,
                workspace_id, workspace_name, relationship_type, datetime.now()
            ])
        logger.info(f"Recorded relationship: {report_name} -> {semantic_model_name}")
        return relationship_id

    def get_version_history(self, artifact_name: str, artifact_type: Optional[str] = None) -> List[Dict]:
        with self._db() as conn:
            if artifact_type:
                result = conn.execute("""
                    SELECT * FROM downloads
                    WHERE artifact_name = ? AND artifact_type = ?
                    ORDER BY download_timestamp DESC
                """, [artifact_name, artifact_type]).fetchall()
            else:
                result = conn.execute("""
                    SELECT * FROM downloads
                    WHERE artifact_name = ?
                    ORDER BY download_timestamp DESC
                """, [artifact_name]).fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def get_workspace_deployments(self, workspace_id: str) -> List[Dict]:
        with self._db() as conn:
            result = conn.execute("""
                SELECT * FROM uploads
                WHERE workspace_id = ?
                ORDER BY upload_timestamp DESC
            """, [workspace_id]).fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def cleanup_orphaned_entries(self) -> int:
        with self._db() as conn:
            mappings = conn.execute("SELECT id, local_file_path FROM workspace_mappings").fetchall()
            orphaned_ids = [mid for mid, fp in mappings if not Path(fp).exists()]
            if orphaned_ids:
                placeholders = ','.join(['?'] * len(orphaned_ids))
                conn.execute(f"DELETE FROM workspace_mappings WHERE id IN ({placeholders})", orphaned_ids)
                logger.info(f"Removed {len(orphaned_ids)} orphaned mapping entries")
        return len(orphaned_ids) if 'orphaned_ids' in dir() else 0

    # ========== Deployment Configuration Methods (v2) ==========

    def create_deployment_profile(
        self,
        profile_name: str,
        target_workspace_id: Optional[str] = None,
        target_workspace_name: Optional[str] = None,
        environment_type: str = 'development',
        description: Optional[str] = None,
        stage_order: Optional[int] = None
    ) -> int:
        with self._db() as conn:
            profile_id = self._next_id(conn, 'deployment_profiles')
            conn.execute("""
                INSERT INTO deployment_profiles (
                    id, profile_name, description, target_workspace_id, target_workspace_name,
                    environment_type, stage_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [profile_id, profile_name, description, target_workspace_id, target_workspace_name,
                  environment_type, stage_order])
        logger.info(f"Created deployment profile: {profile_name} (ID: {profile_id})")
        return profile_id

    def update_deployment_profile(
        self,
        profile_name: str,
        target_workspace_id: Optional[str] = None,
        target_workspace_name: Optional[str] = None,
        stage_order: Optional[int] = None,
        environment_type: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        updates, params = [], []
        if target_workspace_id is not None:
            updates.append("target_workspace_id = ?"); params.append(target_workspace_id)
        if target_workspace_name is not None:
            updates.append("target_workspace_name = ?"); params.append(target_workspace_name)
        if stage_order is not None:
            updates.append("stage_order = ?"); params.append(stage_order)
        if environment_type is not None:
            updates.append("environment_type = ?"); params.append(environment_type)
        if description is not None:
            updates.append("description = ?"); params.append(description)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(profile_name)
        with self._db() as conn:
            conn.execute(f"UPDATE deployment_profiles SET {', '.join(updates)} WHERE profile_name = ?", params)
        logger.info(f"Updated deployment profile: {profile_name}")
        return True

    def get_deployment_profile(self, profile_name: str) -> Optional[Dict]:
        with self._db() as conn:
            result = conn.execute(
                "SELECT * FROM deployment_profiles WHERE profile_name = ?", [profile_name]
            ).fetchone()
            if result:
                columns = [desc[0] for desc in conn.description]
                return dict(zip(columns, result))
        return None

    def get_deployment_profile_by_id(self, profile_id: int) -> Optional[Dict]:
        with self._db() as conn:
            result = conn.execute(
                "SELECT * FROM deployment_profiles WHERE id = ?", [profile_id]
            ).fetchone()
            if result:
                columns = [desc[0] for desc in conn.description]
                return dict(zip(columns, result))
        return None

    def list_deployment_profiles(self) -> List[Dict]:
        with self._db() as conn:
            result = conn.execute("SELECT * FROM deployment_profiles ORDER BY profile_name").fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def create_semantic_model_config(
        self,
        model_name: str,
        target_workspace_id: str,
        target_workspace_name: str,
        local_path_pattern: Optional[str] = None,
        profile_id: Optional[int] = None,
        auto_deploy: bool = False,
        notes: Optional[str] = None
    ) -> int:
        with self._db() as conn:
            config_id = self._next_id(conn, 'semantic_model_configs')
            conn.execute("""
                INSERT INTO semantic_model_configs (
                    id, model_name, local_path_pattern, target_workspace_id, target_workspace_name,
                    profile_id, auto_deploy, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                config_id,
                model_name, local_path_pattern, target_workspace_id, target_workspace_name,
                profile_id, auto_deploy, notes
            ])
        logger.info(f"Created semantic model config: {model_name} -> {target_workspace_name}")
        return config_id

    def get_semantic_model_config(self, model_name: str, profile_id: Optional[int] = None) -> Optional[Dict]:
        with self._db() as conn:
            if profile_id is not None:
                result = conn.execute(
                    "SELECT * FROM semantic_model_configs WHERE model_name = ? AND profile_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    [model_name, profile_id]
                ).fetchone()
            else:
                result = conn.execute(
                    "SELECT * FROM semantic_model_configs WHERE model_name = ? ORDER BY created_at DESC LIMIT 1",
                    [model_name]
                ).fetchone()
            if result:
                columns = [desc[0] for desc in conn.description]
                return dict(zip(columns, result))
        return None

    def list_semantic_model_configs(self, profile_id: Optional[int] = None) -> List[Dict]:
        with self._db() as conn:
            if profile_id:
                result = conn.execute(
                    "SELECT * FROM semantic_model_configs WHERE profile_id = ? ORDER BY model_name",
                    [profile_id]
                ).fetchall()
            else:
                result = conn.execute("SELECT * FROM semantic_model_configs ORDER BY model_name").fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def create_report_config(
        self,
        report_name: str,
        target_workspace_id: str,
        target_workspace_name: str,
        target_semantic_model_id: Optional[str] = None,
        target_semantic_model_name: Optional[str] = None,
        target_model_workspace_id: Optional[str] = None,
        target_model_workspace_name: Optional[str] = None,
        local_path_pattern: Optional[str] = None,
        profile_id: Optional[int] = None,
        auto_deploy: bool = False,
        auto_rebind: bool = True,
        notes: Optional[str] = None
    ) -> int:
        with self._db() as conn:
            config_id = self._next_id(conn, 'report_configs')
            conn.execute("""
                INSERT INTO report_configs (
                    id, report_name, local_path_pattern, target_workspace_id, target_workspace_name,
                    target_semantic_model_id, target_semantic_model_name,
                    target_model_workspace_id, target_model_workspace_name,
                    profile_id, auto_deploy, auto_rebind, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                config_id,
                report_name, local_path_pattern, target_workspace_id, target_workspace_name,
                target_semantic_model_id, target_semantic_model_name,
                target_model_workspace_id, target_model_workspace_name,
                profile_id, auto_deploy, auto_rebind, notes
            ])
        logger.info(f"Created report config: {report_name} -> {target_workspace_name}")
        return config_id

    def get_report_config(self, report_name: str, profile_id: Optional[int] = None) -> Optional[Dict]:
        with self._db() as conn:
            if profile_id is not None:
                result = conn.execute(
                    "SELECT * FROM report_configs WHERE report_name = ? AND profile_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    [report_name, profile_id]
                ).fetchone()
            else:
                result = conn.execute(
                    "SELECT * FROM report_configs WHERE report_name = ? ORDER BY created_at DESC LIMIT 1",
                    [report_name]
                ).fetchone()
            if result:
                columns = [desc[0] for desc in conn.description]
                return dict(zip(columns, result))
        return None

    def list_report_configs(self, profile_id: Optional[int] = None) -> List[Dict]:
        with self._db() as conn:
            if profile_id:
                result = conn.execute(
                    "SELECT * FROM report_configs WHERE profile_id = ? ORDER BY report_name",
                    [profile_id]
                ).fetchall()
            else:
                result = conn.execute("SELECT * FROM report_configs ORDER BY report_name").fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def update_semantic_model_config(
        self,
        model_name: str,
        target_workspace_id: Optional[str] = None,
        target_workspace_name: Optional[str] = None,
        auto_deploy: Optional[bool] = None,
        notes: Optional[str] = None,
        profile_id: Optional[int] = None
    ) -> bool:
        updates, params = [], []
        if target_workspace_id is not None:
            updates.append("target_workspace_id = ?"); params.append(target_workspace_id)
        if target_workspace_name is not None:
            updates.append("target_workspace_name = ?"); params.append(target_workspace_name)
        if auto_deploy is not None:
            updates.append("auto_deploy = ?"); params.append(auto_deploy)
        if notes is not None:
            updates.append("notes = ?"); params.append(notes)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        where = "model_name = ?"
        params.append(model_name)
        if profile_id is not None:
            where += " AND profile_id = ?"
            params.append(profile_id)
        with self._db() as conn:
            conn.execute(f"UPDATE semantic_model_configs SET {', '.join(updates)} WHERE {where}", params)
        logger.info(f"Updated semantic model config: {model_name}")
        return True

    def update_report_config(
        self,
        report_name: str,
        target_workspace_id: Optional[str] = None,
        target_workspace_name: Optional[str] = None,
        target_semantic_model_name: Optional[str] = None,
        target_model_workspace_name: Optional[str] = None,
        auto_deploy: Optional[bool] = None,
        auto_rebind: Optional[bool] = None,
        notes: Optional[str] = None,
        profile_id: Optional[int] = None
    ) -> bool:
        updates, params = [], []
        if target_workspace_id is not None:
            updates.append("target_workspace_id = ?"); params.append(target_workspace_id)
        if target_workspace_name is not None:
            updates.append("target_workspace_name = ?"); params.append(target_workspace_name)
        if target_semantic_model_name is not None:
            updates.append("target_semantic_model_name = ?"); params.append(target_semantic_model_name)
        if target_model_workspace_name is not None:
            updates.append("target_model_workspace_name = ?"); params.append(target_model_workspace_name)
        if auto_deploy is not None:
            updates.append("auto_deploy = ?"); params.append(auto_deploy)
        if auto_rebind is not None:
            updates.append("auto_rebind = ?"); params.append(auto_rebind)
        if notes is not None:
            updates.append("notes = ?"); params.append(notes)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        where = "report_name = ?"
        params.append(report_name)
        if profile_id is not None:
            where += " AND profile_id = ?"
            params.append(profile_id)
        with self._db() as conn:
            conn.execute(f"UPDATE report_configs SET {', '.join(updates)} WHERE {where}", params)
        logger.info(f"Updated report config: {report_name}")
        return True

    # ========== Projects & Environment Promotion (v3) ==========

    def create_project(self, project_name: str, description: Optional[str] = None) -> int:
        with self._db() as conn:
            project_id = self._next_id(conn, 'projects')
            conn.execute(
                "INSERT INTO projects (id, project_name, description) VALUES (?, ?, ?)",
                [project_id, project_name, description]
            )
        logger.info(f"Created project: {project_name} (ID: {project_id})")
        return project_id

    def get_project_by_name(self, project_name: str) -> Optional[Dict]:
        with self._db() as conn:
            result = conn.execute(
                "SELECT * FROM projects WHERE project_name = ?", [project_name]
            ).fetchone()
            if result:
                columns = [desc[0] for desc in conn.description]
                return dict(zip(columns, result))
        return None

    def list_projects(self) -> List[Dict]:
        with self._db() as conn:
            result = conn.execute("SELECT * FROM projects ORDER BY project_name").fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def add_project_artifact(
        self,
        project_id: int,
        artifact_type: str,
        artifact_name: str,
        rebind_to_artifact_name: Optional[str] = None,
        sequence_order: Optional[int] = None,
        notes: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> int:
        with self._db() as conn:
            artifact_id = self._next_id(conn, 'project_artifacts')
            conn.execute("""
                INSERT INTO project_artifacts (
                    id, project_id, artifact_type, artifact_name, rebind_to_artifact_name,
                    sequence_order, notes, folder_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [artifact_id, project_id, artifact_type, artifact_name, rebind_to_artifact_name,
                  sequence_order, notes, folder_path])
        logger.info(f"Added project artifact: {artifact_type}/{artifact_name} -> project {project_id}")
        return artifact_id

    def list_project_artifacts(self, project_id: int) -> List[Dict]:
        with self._db() as conn:
            result = conn.execute(
                "SELECT * FROM project_artifacts WHERE project_id = ? ORDER BY artifact_type, artifact_name",
                [project_id]
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def remove_project_artifact(self, project_id: int, artifact_type: str, artifact_name: str) -> bool:
        with self._db() as conn:
            existing = conn.execute(
                "SELECT id FROM project_artifacts WHERE project_id = ? AND artifact_type = ? AND artifact_name = ?",
                [project_id, artifact_type, artifact_name]
            ).fetchone()
            if not existing:
                return False
            conn.execute("DELETE FROM project_artifacts WHERE id = ?", [existing[0]])
        logger.info(f"Removed project artifact: {artifact_type}/{artifact_name} from project {project_id}")
        return True

    def upsert_project_environment_workspace(
        self,
        project_id: int,
        profile_id: int,
        artifact_type: Optional[str],
        workspace_id: str,
        workspace_name: str
    ) -> int:
        """
        Register (or update) the workspace a project should use for a given
        environment, optionally scoped to one artifact type. artifact_type=None
        means "combined" — applies to both SemanticModel and Report for that
        (project, environment) when no more specific split override exists.
        """
        with self._db() as conn:
            if artifact_type is None:
                existing = conn.execute(
                    "SELECT id FROM project_environment_workspaces "
                    "WHERE project_id = ? AND profile_id = ? AND artifact_type IS NULL",
                    [project_id, profile_id]
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM project_environment_workspaces "
                    "WHERE project_id = ? AND profile_id = ? AND artifact_type = ?",
                    [project_id, profile_id, artifact_type]
                ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE project_environment_workspaces "
                    "SET workspace_id = ?, workspace_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    [workspace_id, workspace_name, existing[0]]
                )
                return existing[0]

            row_id = self._next_id(conn, 'project_environment_workspaces')
            conn.execute("""
                INSERT INTO project_environment_workspaces (
                    id, project_id, profile_id, artifact_type, workspace_id, workspace_name
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, [row_id, project_id, profile_id, artifact_type, workspace_id, workspace_name])
            return row_id

    def list_project_environment_workspaces(
        self, project_id: int, profile_id: Optional[int] = None
    ) -> List[Dict]:
        with self._db() as conn:
            if profile_id is not None:
                result = conn.execute(
                    "SELECT * FROM project_environment_workspaces WHERE project_id = ? AND profile_id = ?",
                    [project_id, profile_id]
                ).fetchall()
            else:
                result = conn.execute(
                    "SELECT * FROM project_environment_workspaces WHERE project_id = ?", [project_id]
                ).fetchall()
            columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def get_environment_artifact_state(
        self, project_id: int, profile_id: int, artifact_type: str, artifact_name: str
    ) -> Optional[Dict]:
        with self._db() as conn:
            result = conn.execute("""
                SELECT * FROM environment_artifact_state
                WHERE project_id = ? AND profile_id = ? AND artifact_type = ? AND artifact_name = ?
            """, [project_id, profile_id, artifact_type, artifact_name]).fetchone()
            if result:
                columns = [desc[0] for desc in conn.description]
                return dict(zip(columns, result))
        return None

    def upsert_environment_artifact_state(
        self,
        project_id: int,
        profile_id: int,
        artifact_type: str,
        artifact_name: str,
        workspace_item_id: Optional[str],
        workspace_id: Optional[str],
        workspace_name: Optional[str],
        definition_hash: Optional[str],
        source_profile_id: Optional[int],
        last_operation: str,
        promotion_event_id: Optional[int] = None,
        updated_by: Optional[str] = None
    ) -> None:
        with self._db() as conn:
            existing = conn.execute("""
                SELECT id FROM environment_artifact_state
                WHERE project_id = ? AND profile_id = ? AND artifact_type = ? AND artifact_name = ?
            """, [project_id, profile_id, artifact_type, artifact_name]).fetchone()

            if existing:
                conn.execute("""
                    UPDATE environment_artifact_state
                    SET workspace_item_id = ?, workspace_id = ?, workspace_name = ?, definition_hash = ?,
                        source_profile_id = ?, last_operation = ?, promotion_event_id = ?, updated_by = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, [workspace_item_id, workspace_id, workspace_name, definition_hash,
                      source_profile_id, last_operation, promotion_event_id, updated_by, existing[0]])
            else:
                state_id = self._next_id(conn, 'environment_artifact_state')
                conn.execute("""
                    INSERT INTO environment_artifact_state (
                        id, project_id, profile_id, artifact_type, artifact_name, workspace_item_id,
                        workspace_id, workspace_name, definition_hash, source_profile_id, last_operation,
                        promotion_event_id, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [state_id, project_id, profile_id, artifact_type, artifact_name, workspace_item_id,
                      workspace_id, workspace_name, definition_hash, source_profile_id, last_operation,
                      promotion_event_id, updated_by])

    def record_promotion_event(
        self,
        project_id: int,
        operation: str,
        to_profile_id: int,
        from_profile_id: Optional[int] = None,
        artifact_summary: Optional[str] = None,
        drift_detected: bool = False,
        drift_confirmed: bool = False,
        status: str = 'success',
        error_message: Optional[str] = None,
        initiated_by: Optional[str] = None
    ) -> int:
        with self._db() as conn:
            event_id = self._next_id(conn, 'promotion_events')
            conn.execute("""
                INSERT INTO promotion_events (
                    id, project_id, operation, from_profile_id, to_profile_id, artifact_summary,
                    drift_detected, drift_confirmed, status, error_message, initiated_by,
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [event_id, project_id, operation, from_profile_id, to_profile_id, artifact_summary,
                  drift_detected, drift_confirmed, status, error_message, initiated_by,
                  datetime.now(), datetime.now()])
        logger.info(f"Recorded promotion event: project {project_id} {operation} -> profile {to_profile_id} ({status})")
        return event_id

    def get_deployment_stats(self) -> Dict:
        with self._db() as conn:
            return {
                'total_downloads': conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0],
                'total_uploads': conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0],
                'active_mappings': conn.execute("SELECT COUNT(*) FROM workspace_mappings").fetchone()[0],
                'deployment_profiles': conn.execute("SELECT COUNT(*) FROM deployment_profiles").fetchone()[0],
                'semantic_model_configs': conn.execute("SELECT COUNT(*) FROM semantic_model_configs").fetchone()[0],
                'report_configs': conn.execute("SELECT COUNT(*) FROM report_configs").fetchone()[0],
                'recent_deployments': conn.execute(
                    "SELECT COUNT(*) FROM uploads WHERE upload_timestamp >= current_timestamp - interval 7 days"
                ).fetchone()[0]
            }
