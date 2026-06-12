"""
DuckDB Metadata Database Schema and Operations

Manages metadata tracking for Power BI assets including version history,
workspace mappings, and report-to-model relationships.
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import duckdb

logger = logging.getLogger(__name__)


class MetadataDatabase:
    """
    DuckDB database for metadata tracking.
    Each public method opens and closes its own connection so the file
    is never held open between operations (avoids cross-process lock conflicts).
    """

    SCHEMA_VERSION = 2

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
        """Open a fresh connection, yield it, then close it."""
        conn = duckdb.connect(str(self.db_path))
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
        description: Optional[str] = None
    ) -> int:
        with self._db() as conn:
            profile_id = self._next_id(conn, 'deployment_profiles')
            conn.execute("""
                INSERT INTO deployment_profiles (
                    id, profile_name, description, target_workspace_id, target_workspace_name, environment_type
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, [profile_id, profile_name, description, target_workspace_id, target_workspace_name, environment_type])
        logger.info(f"Created deployment profile: {profile_name} (ID: {profile_id})")
        return profile_id

    def get_deployment_profile(self, profile_name: str) -> Optional[Dict]:
        with self._db() as conn:
            result = conn.execute(
                "SELECT * FROM deployment_profiles WHERE profile_name = ?", [profile_name]
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

    def get_semantic_model_config(self, model_name: str) -> Optional[Dict]:
        with self._db() as conn:
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

    def get_report_config(self, report_name: str) -> Optional[Dict]:
        with self._db() as conn:
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
        notes: Optional[str] = None
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
        params.append(model_name)
        with self._db() as conn:
            conn.execute(f"UPDATE semantic_model_configs SET {', '.join(updates)} WHERE model_name = ?", params)
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
        notes: Optional[str] = None
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
        params.append(report_name)
        with self._db() as conn:
            conn.execute(f"UPDATE report_configs SET {', '.join(updates)} WHERE report_name = ?", params)
        logger.info(f"Updated report config: {report_name}")
        return True

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
