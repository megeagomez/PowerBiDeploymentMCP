"""
Versioning Manager

Handles automatic file versioning for downloads outside Git repositories.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .git_utils import is_git_repository

logger = logging.getLogger(__name__)


class VersioningConfig:
    """Configuration for versioning behavior"""
    
    def __init__(
        self,
        enabled: Optional[bool] = None,
        format: str = "%Y%m%d_%H%M%S",
        db_path: Optional[Path] = None
    ):
        """
        Initialize versioning configuration
        
        Args:
            enabled: Force enable/disable versioning (None = auto-detect)
            format: Timestamp format for version suffixes
            db_path: Path to metadata database
        """
        self.enabled = enabled
        self.format = format
        self.db_path = db_path


class VersioningManager:
    """
    Manages automatic file versioning based on Git detection
    """
    
    def __init__(self, config: Optional[VersioningConfig] = None):
        """
        Initialize versioning manager
        
        Args:
            config: Versioning configuration
        """
        self.config = config or VersioningConfig()
        logger.info(f"Versioning manager initialized (format: {self.config.format})")
    
    def should_version(self, target_path: Path) -> bool:
        """
        Determine if versioning should be applied for a given path
        
        Args:
            target_path: Path where file will be saved
            
        Returns:
            True if versioning should be applied, False otherwise
        """
        # Check explicit configuration first
        if self.config.enabled is not None:
            return self.config.enabled
        
        # Auto-detect based on Git repository
        is_git = is_git_repository(target_path.parent)
        should_version = not is_git
        
        logger.debug(f"Versioning for {target_path}: {should_version} (Git detected: {is_git})")
        return should_version
    
    def get_versioned_path(self, original_path: Path) -> tuple[Path, str]:
        """
        Get versioned file path with timestamp suffix
        
        Args:
            original_path: Original file path
            
        Returns:
            Tuple of (versioned_path, version_suffix)
        """
        timestamp = datetime.now().strftime(self.config.format)
        
        # Split into stem and extension
        stem = original_path.stem
        suffix = original_path.suffix
        
        # Create versioned filename
        versioned_name = f"{stem}_{timestamp}{suffix}"
        versioned_path = original_path.parent / versioned_name
        
        logger.debug(f"Versioned path: {versioned_path}")
        return versioned_path, timestamp
    
    def apply_versioning(self, target_path: Path) -> tuple[Path, Optional[str]]:
        """
        Apply versioning logic to a target path
        
        Args:
            target_path: Intended file path
            
        Returns:
            Tuple of (actual_path, version_suffix)
            - If versioning applied: (versioned_path, timestamp)
            - If no versioning: (original_path, None)
        """
        if self.should_version(target_path):
            versioned_path, version_suffix = self.get_versioned_path(target_path)
            logger.info(f"Applying versioning: {target_path.name} -> {versioned_path.name}")
            return versioned_path, version_suffix
        else:
            logger.info(f"No versioning applied: {target_path.name}")
            return target_path, None
