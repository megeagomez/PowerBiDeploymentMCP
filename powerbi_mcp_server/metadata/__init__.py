# Metadata and versioning module

from .manager import MetadataManager
from .versioning import VersioningConfig, VersioningManager
from .database import MetadataDatabase
from .git_utils import is_git_repository, get_git_root
from .deployment_config import DeploymentConfigManager

__all__ = [
    "MetadataManager",
    "VersioningConfig",
    "VersioningManager",
    "MetadataDatabase",
    "DeploymentConfigManager",
    "is_git_repository",
    "get_git_root",
]
