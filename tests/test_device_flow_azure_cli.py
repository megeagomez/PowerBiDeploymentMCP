"""
Tests for the `az login` session-reuse auth path (AzureCliCredential).

All tests mock AzureCliCredential at its import site inside
powerbi_mcp_server.auth.device_flow — no real `az` subprocess is ever launched.
"""

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from azure.core.credentials import AccessToken
from azure.identity import CredentialUnavailableError

from powerbi_mcp_server.auth import device_flow
from powerbi_mcp_server.auth.authenticator import AuthenticationRequired, PowerBIAuthenticator
from powerbi_mcp_server.auth.token_manager import AuthenticationStateManager


def _fake_jwt(claims: dict) -> str:
    """Build a JWT-shaped string with a real base64url payload (unsigned)."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"header.{payload}.signature"


FUTURE_EPOCH = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())


class FakeAzureCliCredential:
    """Stand-in for azure.identity.AzureCliCredential in tests."""

    def __init__(self, token=None, error=None):
        self._token = token
        self._error = error

    def get_token(self, *scopes):
        if self._error:
            raise self._error
        return self._token


# ---------------------------------------------------------------------------
# azure_cli_authenticate()
# ---------------------------------------------------------------------------

def test_azure_cli_authenticate_success(monkeypatch):
    jwt = _fake_jwt({"name": "Ada Lovelace", "upn": "ada@example.com"})
    fake_credential = FakeAzureCliCredential(token=AccessToken(jwt, FUTURE_EPOCH))
    monkeypatch.setattr(device_flow, "AzureCliCredential", lambda: fake_credential)

    result = device_flow.azure_cli_authenticate()

    assert result is not None
    assert result["powerbi"] == jwt
    assert result["user_name"] == "Ada Lovelace"
    assert result["user_email"] == "ada@example.com"
    assert result["auth_method"] == "az_cli"
    assert result["principal"] == "user:ada@example.com"
    assert isinstance(result["expires_at"], datetime)


def test_azure_cli_authenticate_unavailable_returns_none(monkeypatch):
    fake_credential = FakeAzureCliCredential(error=CredentialUnavailableError("az CLI not found"))
    monkeypatch.setattr(device_flow, "AzureCliCredential", lambda: fake_credential)

    result = device_flow.azure_cli_authenticate()

    assert result is None


def test_azure_cli_authenticate_unexpected_error_propagates(monkeypatch):
    fake_credential = FakeAzureCliCredential(error=RuntimeError("something else broke"))
    monkeypatch.setattr(device_flow, "AzureCliCredential", lambda: fake_credential)

    with pytest.raises(RuntimeError):
        device_flow.azure_cli_authenticate()


# ---------------------------------------------------------------------------
# _decode_jwt_claims()
# ---------------------------------------------------------------------------

def test_decode_jwt_claims_valid_payload():
    jwt = _fake_jwt({"name": "Test User", "upn": "test@example.com"})
    claims = device_flow._decode_jwt_claims(jwt)
    assert claims == {"name": "Test User", "upn": "test@example.com"}


def test_decode_jwt_claims_malformed_returns_empty_dict():
    assert device_flow._decode_jwt_claims("not-a-jwt") == {}
    assert device_flow._decode_jwt_claims("") == {}
    assert device_flow._decode_jwt_claims("a.b.c") == {}  # "b" isn't valid base64 JSON


# ---------------------------------------------------------------------------
# PowerBIAuthenticator.ensure_authenticated() precedence
# ---------------------------------------------------------------------------

@pytest.fixture
def authenticator(tmp_path, monkeypatch):
    auth = PowerBIAuthenticator()
    auth.state_manager = AuthenticationStateManager(cache_dir=tmp_path)
    # Neutralize the two earlier precedence steps so each test controls exactly
    # which step succeeds.
    monkeypatch.setattr("powerbi_mcp_server.auth.authenticator.try_silent_auth", lambda: None)
    return auth


def test_ensure_authenticated_uses_azure_cli_when_silent_auth_fails(authenticator, monkeypatch):
    jwt = _fake_jwt({"name": "Ada Lovelace", "upn": "ada@example.com"})
    az_result = {
        "powerbi": jwt,
        "user_name": "Ada Lovelace",
        "user_email": "ada@example.com",
        "expires_at": datetime.now() + timedelta(hours=1),
        "auth_method": "az_cli",
        "principal": "user:ada@example.com",
    }
    monkeypatch.setattr(
        "powerbi_mcp_server.auth.authenticator.azure_cli_authenticate", lambda: az_result
    )

    token = asyncio.run(authenticator.ensure_authenticated())

    assert token == jwt
    assert authenticator.state_manager.get_current_token() == jwt


def test_ensure_authenticated_raises_when_all_silent_paths_fail(authenticator, monkeypatch):
    monkeypatch.setattr(
        "powerbi_mcp_server.auth.authenticator.azure_cli_authenticate", lambda: None
    )

    with pytest.raises(AuthenticationRequired):
        asyncio.run(authenticator.ensure_authenticated())


# TODO once POWERBI_MCP_* service-principal env-var wiring lands: add a case
# verifying SP takes precedence over az-cli reuse when both are available.
