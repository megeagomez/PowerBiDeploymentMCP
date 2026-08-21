"""
Token Storage and Management with DPAPI Encryption

Handles secure token caching, refresh logic, and authentication state management.
"""

import json
import logging
import win32crypt
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TokenStorageError(Exception):
    """Raised when token storage operations fail"""
    pass


def encrypt_data(data: str) -> bytes:
    """Encrypt a string using Windows DPAPI (current user scope)."""
    try:
        return win32crypt.CryptProtectData(
            data.encode('utf-8'), None, None, None, None, 0
        )
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise TokenStorageError(f"Failed to encrypt data: {e}")


def decrypt_data(encrypted_data: bytes) -> str:
    """Decrypt DPAPI-protected bytes back to a string."""
    try:
        decrypted = win32crypt.CryptUnprotectData(encrypted_data, None, None, None, 0)
        return decrypted[1].decode('utf-8')
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise TokenStorageError(f"Failed to decrypt data: {e}")


class AuthenticationStateManager:
    """
    Manages authentication state including token caching and refresh
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the authentication state manager
        
        Args:
            cache_dir: Directory for token cache (default: .powerbi-mcp-deployment/cache)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".powerbi-mcp-deployment" / "cache"
        
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = self.cache_dir / "tokens.encrypted"
        
        self._current_state: Optional[Dict] = None
        logger.info(f"Token cache directory: {self.cache_dir}")
    
    def _encrypt_data(self, data: str) -> bytes:
        """Encrypt data using Windows DPAPI"""
        return encrypt_data(data)

    def _decrypt_data(self, encrypted_data: bytes) -> str:
        """Decrypt data using Windows DPAPI"""
        return decrypt_data(encrypted_data)
    
    def save_tokens(self, auth_result: Dict) -> None:
        """
        Save authentication tokens securely
        
        Args:
            auth_result: Authentication result dictionary containing tokens
        """
        logger.info("Saving authentication tokens")
        
        # Prepare data for storage (exclude credential objects)
        storage_data = {
            "powerbi_token": auth_result.get("powerbi"),
            "user_name": auth_result.get("user_name"),
            "user_email": auth_result.get("user_email"),
            "auth_method": auth_result.get("auth_method", "device_flow"),
            "principal": auth_result.get("principal"),
            "expires_at": auth_result.get("expires_at").isoformat() if isinstance(auth_result.get("expires_at"), datetime) else auth_result.get("expires_at"),
            "saved_at": datetime.now().isoformat()
        }
        
        # Serialize to JSON
        json_data = json.dumps(storage_data)
        
        # Encrypt and save
        encrypted_data = self._encrypt_data(json_data)
        self.token_file.write_bytes(encrypted_data)
        
        # Update current state
        self._current_state = auth_result
        
        logger.info("Tokens saved successfully")
    
    def load_tokens(self) -> Optional[Dict]:
        """
        Load and decrypt authentication tokens
        
        Returns:
            Dictionary with token data, or None if no valid cache exists
        """
        if not self.token_file.exists():
            logger.info("No token cache found")
            return None
        
        try:
            encrypted_data = self.token_file.read_bytes()
            json_data = self._decrypt_data(encrypted_data)
            storage_data = json.loads(json_data)
            
            # Parse expiration time
            expires_at_str = storage_data.get("expires_at")
            if expires_at_str:
                storage_data["expires_at"] = datetime.fromisoformat(expires_at_str)
            
            logger.info(f"Loaded tokens for user: {storage_data.get('user_email')}")
            return storage_data
            
        except Exception as e:
            logger.warning(f"Failed to load token cache: {e}")
            return None
    
    def is_token_valid(self, token_data: Optional[Dict] = None) -> bool:
        """
        Check if a token is still valid
        
        Args:
            token_data: Token data dictionary (uses current state if None)
            
        Returns:
            True if token is valid, False otherwise
        """
        if token_data is None:
            token_data = self._current_state
        
        if not token_data:
            return False
        
        expires_at = token_data.get("expires_at")
        if not expires_at:
            return False
        
        # Consider token invalid if it expires in less than 5 minutes
        buffer_time = timedelta(minutes=5)
        is_valid = datetime.now() + buffer_time < expires_at
        
        logger.debug(f"Token valid: {is_valid}, expires at: {expires_at}")
        return is_valid
    
    def needs_refresh(self) -> bool:
        """
        Check if current token needs refresh

        Returns:
            True if token needs refresh, False otherwise
        """
        if not self._current_state:
            # Try to load from cache
            self._current_state = self.load_tokens()

        return not self.is_token_valid()

    def get_current_token(self) -> Optional[str]:
        """
        Get the current valid Power BI token.

        If the in-memory state is missing or expired, reload from disk before
        giving up — another process (e.g. a second MCP server instance) may
        have refreshed the token on disk since this state was last loaded.

        Returns:
            Token string if valid, None otherwise
        """
        if not self._current_state:
            self._current_state = self.load_tokens()

        if not self.is_token_valid(self._current_state):
            reloaded = self.load_tokens()
            if reloaded and self.is_token_valid(reloaded):
                logger.info("In-memory token was stale; picked up refreshed token from disk")
                self._current_state = reloaded

        if self.is_token_valid(self._current_state):
            token = self._current_state.get("powerbi_token") or self._current_state.get("powerbi")
            if token:
                logger.debug(f"Returning valid token for {self._current_state.get('user_email')}")
                return token

        logger.debug("No valid token available")
        return None
    
    def get_user_info(self) -> Optional[Dict]:
        """
        Get authenticated user information
        
        Returns:
            Dictionary with user_name and user_email, or None
        """
        if not self._current_state:
            self._current_state = self.load_tokens()
        
        if self._current_state:
            return {
                "user_name": self._current_state.get("user_name"),
                "user_email": self._current_state.get("user_email"),
                "auth_method": self._current_state.get("auth_method")
            }
        
        return None
    
    def clear_tokens(self) -> None:
        """Clear all cached tokens"""
        logger.info("Clearing token cache")
        
        if self.token_file.exists():
            self.token_file.unlink()
        
        self._current_state = None
        logger.info("Token cache cleared")
    
    def update_state(self, auth_result: Dict) -> None:
        """
        Update the current authentication state.
        Normalizes the key from "powerbi" (device flow) to "powerbi_token" (storage format)
        so in-memory state and disk state are always consistent.
        """
        normalized = dict(auth_result)
        if "powerbi" in normalized and "powerbi_token" not in normalized:
            normalized["powerbi_token"] = normalized.pop("powerbi")
        self._current_state = normalized
        self.save_tokens(auth_result)  # save_tokens handles its own key mapping
