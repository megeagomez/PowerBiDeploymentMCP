"""
Metadata Manager

High-level API for metadata operations including versioning and database management.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .database import MetadataDatabase
from .versioning import VersioningManager, VersioningConfig
from .git_utils import is_git_repository

logger = logging.getLogger(__name__)


class MetadataManager:
    """
    High-level manager for metadata and versioning operations
    """
    
    def __init__(self, config: Optional[VersioningConfig] = None):
        """
        Initialize metadata manager
        
        Args:
            config: Versioning configuration
        """
        self.config = config or VersioningConfig()
        self.database = MetadataDatabase(self.config.db_path)
        self.versioning = VersioningManager(self.config)
        logger.info("Metadata manager initialized")
    
    async def initialize(self) -> None:
        """Initialize database schema"""
        self.database.initialize_schema()
    
    async def close(self) -> None:
        """Close database connection"""
        self.database.close()
    
    # Download operations
    
    def prepare_download_path(self, base_path: Path) -> tuple[Path, Optional[str]]:
        """
        Prepare download path with versioning if needed
        
        Args:
            base_path: Base file path
            
        Returns:
            Tuple of (actual_path, version_suffix)
        """
        return self.versioning.apply_versioning(base_path)
    
    def record_download(
        self,
        artifact_name: str,
        artifact_type: str,
        workspace_id: str,
        workspace_name: str,
        local_file_path: Path,
        version_suffix: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> int:
        """Record a download operation in metadata database"""
        file_size = local_file_path.stat().st_size if local_file_path.exists() else None
        
        return self.database.record_download(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            local_file_path=str(local_file_path),
            version_suffix=version_suffix,
            user_email=user_email,
            file_size_bytes=file_size
        )
    
    # Upload operations
    
    def record_upload(
        self,
        artifact_name: str,
        artifact_type: str,
        workspace_id: str,
        workspace_name: str,
        source_file_path: Path,
        asset_id: str,
        user_email: Optional[str] = None,
        operation_type: str = 'create'
    ) -> int:
        """Record an upload operation in metadata database"""
        return self.database.record_upload(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            source_file_path=str(source_file_path),
            asset_id=asset_id,
            user_email=user_email,
            operation_type=operation_type
        )
    
    def track_workspace_mapping(
        self,
        local_file_path: Path,
        workspace_id: str,
        workspace_name: str,
        asset_id: str,
        asset_name: str,
        asset_type: str
    ) -> None:
        """Track file-to-workspace mapping"""
        self.database.upsert_workspace_mapping(
            local_file_path=str(local_file_path),
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            asset_id=asset_id,
            asset_name=asset_name,
            asset_type=asset_type
        )
    
    def track_report_model_relationship(
        self,
        report_id: str,
        report_name: str,
        semantic_model_id: str,
        semantic_model_name: str,
        workspace_id: str,
        workspace_name: str
    ) -> int:
        """Track report-to-semantic-model relationship"""
        return self.database.record_report_model_relationship(
            report_id=report_id,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
            semantic_model_name=semantic_model_name,
            workspace_id=workspace_id,
            workspace_name=workspace_name
        )
    
    # Query operations
    
    def get_version_history(self, artifact_name: str, artifact_type: Optional[str] = None) -> List[Dict]:
        """Get version history for an artifact"""
        return self.database.get_version_history(artifact_name, artifact_type)
    
    def get_workspace_deployments(self, workspace_id: str) -> List[Dict]:
        """Get deployment history for a workspace"""
        return self.database.get_workspace_deployments(workspace_id)
    
    # Maintenance operations
    
    def cleanup_orphaned_entries(self) -> int:
        """Remove metadata entries for non-existent files"""
        return self.database.cleanup_orphaned_entries()
    
    def is_git_controlled(self, path: Optional[Path] = None) -> bool:
        """Check if path is under Git control"""
        return is_git_repository(path)
