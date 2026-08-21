"""
Main Authentication API

Provides high-level authentication interface for the MCP server.
"""

import asyncio
import logging
from typing import Dict, Optional

from .device_flow import (
    initiate_device_flow,
    complete_device_flow_sync,
    try_silent_auth,
    azure_cli_authenticate,
    AuthenticationError,
    _executor,
)
from .token_manager import AuthenticationStateManager

logger = logging.getLogger(__name__)


class AuthenticationRequired(Exception):
    """Raised when a tool requires auth but no valid token exists."""
    pass


class PowerBIAuthenticator:
    """High-level authentication manager for Power BI MCP Server."""

    def __init__(self):
        self.state_manager = AuthenticationStateManager()
        self._pending_future: Optional[asyncio.Future] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        return not self.state_manager.needs_refresh() and bool(self.state_manager.get_current_token())

    def get_token(self) -> Optional[str]:
        return self.state_manager.get_current_token()

    def get_tokens(self) -> Optional[Dict]:
        token = self.state_manager.get_current_token()
        if not token:
            return None
        return {"powerbi": token, "user_info": self.state_manager.get_user_info()}

    def get_user_info(self) -> Optional[Dict]:
        return self.state_manager.get_user_info()

    def logout(self) -> None:
        logger.info("Logging out and clearing tokens")
        self.state_manager.clear_tokens()

    async def ensure_authenticated(self) -> str:
        """
        Return a valid token or raise AuthenticationRequired.
        Never blocks waiting for user interaction.
        """
        # 1. Already have a valid cached token (DPAPI store)
        token = self.state_manager.get_current_token()
        if token:
            return token

        # 2. Try MSAL silent cache (handles refresh tokens automatically)
        try:
            result = try_silent_auth()
            if result:
                self.state_manager.update_state(result)
                logger.info(f"Silent auth succeeded for {result.get('user_email')}")
                return result["powerbi"]
        except Exception as e:
            logger.warning(f"Silent auth failed: {e}")

        # 3. Try reusing an existing `az login` session (best-effort, silent)
        try:
            result = azure_cli_authenticate()
            if result:
                self.state_manager.update_state(result)
                logger.info(f"Azure CLI auth succeeded for {result.get('user_email')}")
                return result["powerbi"]
        except Exception as e:
            logger.warning(f"Azure CLI auth failed: {e}")

        # 4. No token available — caller must show Device Flow to the user
        raise AuthenticationRequired(
            "No hay sesión activa. Llama a la herramienta `authenticate` para iniciar el login con Microsoft."
        )

    async def start_device_flow(self) -> str:
        """
        Initiate Device Flow. Returns the user-facing message (URL + code)
        and starts background polling. Non-blocking.
        """
        # If already authenticated, skip
        if self.is_authenticated():
            user_info = self.state_manager.get_user_info() or {}
            return (
                f"✓ Ya estás autenticado como {user_info.get('user_name', 'Usuario')} "
                f"({user_info.get('user_email', '')})"
            )

        # Try silent auth first
        try:
            result = try_silent_auth()
            if result:
                self.state_manager.update_state(result)
                return (
                    f"✓ Autenticado silenciosamente como {result['user_name']} ({result['user_email']})"
                )
        except Exception:
            pass

        # Try reusing an existing `az login` session next
        try:
            result = azure_cli_authenticate()
            if result:
                self.state_manager.update_state(result)
                return (
                    f"✓ Autenticado vía sesión Azure CLI como {result['user_name']} ({result['user_email']})"
                )
        except Exception:
            pass

        # Start device flow
        app, flow, message = initiate_device_flow()

        # Launch background polling (does NOT block the event loop)
        loop = asyncio.get_event_loop()
        self._pending_future = loop.run_in_executor(
            _executor, complete_device_flow_sync, app, flow
        )
        self._pending_future.add_done_callback(self._on_auth_complete)

        logger.info("Device flow initiated, polling in background")
        return (
            f"{message}\n\n"
            "⏳ Esperando que completes la autenticación en el navegador...\n"
            "Una vez autenticado, vuelve a llamar a cualquier herramienta de Power BI."
        )

    def _on_auth_complete(self, future):
        """Callback when background polling finishes."""
        try:
            result = future.result()
            self.state_manager.update_state(result)
            logger.info(f"Background auth completed for {result.get('user_email')}")
        except Exception as e:
            logger.error(f"Background auth failed: {e}")


# Global authenticator instance
_authenticator: Optional[PowerBIAuthenticator] = None


def get_authenticator() -> PowerBIAuthenticator:
    global _authenticator
    if _authenticator is None:
        _authenticator = PowerBIAuthenticator()
    return _authenticator
