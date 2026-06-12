"""
Git Detection Utilities

Detects if the current directory is under Git version control.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_git_repository(path: Optional[Path] = None) -> bool:
    """
    Check if the given path is within a Git repository
    
    Args:
        path: Path to check (default: current working directory)
        
    Returns:
        True if path is in a Git repository, False otherwise
    """
    if path is None:
        path = Path.cwd()
    
    try:
        # Try using git command
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        is_git = result.returncode == 0 and result.stdout.strip() == 'true'
        logger.debug(f"Git detection for {path}: {is_git}")
        return is_git
        
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Git detection failed: {e}")
        return False


def get_git_root(path: Optional[Path] = None) -> Optional[Path]:
    """
    Get the root directory of the Git repository
    
    Args:
        path: Path within the repository (default: current working directory)
        
    Returns:
        Path to Git repository root, or None if not in a Git repository
    """
    if path is None:
        path = Path.cwd()
    
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            git_root = Path(result.stdout.strip())
            logger.debug(f"Git root: {git_root}")
            return git_root
        
        return None
        
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Failed to get Git root: {e}")
        return None
