"""
Authentication Module for Power BI MCP Server

Handles Device Flow authentication and token management for Power BI and OneLake APIs.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import msal
from azure.identity import ClientSecretCredential

from .token_manager import encrypt_data, decrypt_data

logger = logging.getLogger(__name__)

# Constants
TENANT_ID = "common"
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI public client
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
POWERBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]

# Persisted MSAL cache (holds the refresh token) so silent auth works across
# process restarts — without it the user has to redo Device Flow every hour.
_MSAL_CACHE_FILE = Path.home() / ".powerbi-mcp-deployment" / "cache" / "msal_cache.encrypted"

_executor = ThreadPoolExecutor(max_workers=1)


class AuthenticationError(Exception):
    """Raised when authentication fails"""
    pass


def _load_msal_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    try:
        if _MSAL_CACHE_FILE.exists():
            cache.deserialize(decrypt_data(_MSAL_CACHE_FILE.read_bytes()))
    except Exception as e:
        logger.warning(f"Could not load MSAL token cache, starting fresh: {e}")
    return cache


def _save_msal_cache(cache: msal.SerializableTokenCache) -> None:
    if not cache.has_state_changed:
        return
    try:
        _MSAL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MSAL_CACHE_FILE.write_bytes(encrypt_data(cache.serialize()))
        logger.debug("MSAL token cache persisted")
    except Exception as e:
        logger.warning(f"Could not persist MSAL token cache: {e}")


def _get_msal_app() -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=_load_msal_cache()
    )


def try_silent_auth() -> Optional[Dict]:
    """Try to get a token silently from MSAL cache. Returns result dict or None."""
    app = _get_msal_app()
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(POWERBI_SCOPE, account=accounts[0])
    _save_msal_cache(app.token_cache)
    if result and "access_token" in result:
        return _build_auth_result(result)
    return None


def initiate_device_flow() -> Tuple[msal.PublicClientApplication, Dict, str]:
    """
    Start a Device Flow. Returns (app, flow, user_message) without blocking.
    The caller is responsible for completing the flow in a background thread.
    """
    app = _get_msal_app()
    flow = app.initiate_device_flow(scopes=POWERBI_SCOPE)
    if "user_code" not in flow:
        raise AuthenticationError("Error al iniciar flujo de dispositivo")
    return app, flow, flow["message"]


def complete_device_flow_sync(app: msal.PublicClientApplication, flow: Dict) -> Dict:
    """Blocking poll — run in a thread pool, not the event loop."""
    result = app.acquire_token_by_device_flow(flow)
    _save_msal_cache(app.token_cache)
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Error desconocido"))
        raise AuthenticationError(f"Error de autenticación: {error}")
    return _build_auth_result(result)


def _build_auth_result(result: Dict) -> Dict:
    claims = result.get("id_token_claims", {})
    user_name = claims.get("name", "Usuario")
    user_email = claims.get("preferred_username", "")
    expires_at = datetime.now() + timedelta(seconds=result.get("expires_in", 3600))
    return {
        "powerbi": result["access_token"],
        "user_name": user_name,
        "user_email": user_email,
        "expires_at": expires_at,
    }


def service_principal_authenticate(tenant_id: str, client_id: str, client_secret: str) -> Dict:
    """Service Principal authentication for non-interactive deployments."""
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id, authority=authority, client_credential=client_secret
    )
    result = app.acquire_token_for_client(scopes=POWERBI_SCOPE)
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Error desconocido"))
        raise AuthenticationError(f"Error SP: {error}")

    credential = ClientSecretCredential(
        tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
    )
    expires_at = datetime.now() + timedelta(seconds=result.get("expires_in", 3600))
    return {
        "powerbi": result["access_token"],
        "onelake_credential": credential,
        "expires_at": expires_at,
    }
