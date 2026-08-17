from unittest.mock import MagicMock, patch

import pytest
import requests

from powerbi_mcp_server.api.client import PowerBIClient


def _resp(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _http_error(status_code, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    resp.text = str(body or {})
    return requests.exceptions.HTTPError(response=resp)


@pytest.fixture
def client() -> PowerBIClient:
    return PowerBIClient("fake-token")


def test_create_workspace_success_without_capacity(client):
    def side_effect(method, url, **kwargs):
        assert method == 'POST'
        assert url.endswith('/groups')
        return _resp({'id': 'ws-1', 'name': 'Ventas_semantic_dev'})

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect) as mock_req:
        workspace = client.create_workspace("Ventas_semantic_dev")

    assert workspace['id'] == 'ws-1'
    mock_req.assert_called_once()


def test_create_workspace_assigns_capacity_when_given(client):
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs.get('json')))
        if url.endswith('/groups'):
            return _resp({'id': 'ws-1', 'name': 'Ventas_semantic_dev'})
        if url.endswith('/AssignToCapacity'):
            return _resp({})
        raise AssertionError(f"unexpected url {url}")

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        client.create_workspace("Ventas_semantic_dev", capacity_id="cap-123")

    assign_calls = [c for c in calls if c[1].endswith('/AssignToCapacity')]
    assert len(assign_calls) == 1
    assert assign_calls[0][2] == {'capacityId': 'cap-123'}


def test_create_workspace_reuses_on_duplicate_name(client):
    def side_effect(method, url, **kwargs):
        if method == 'POST' and url.endswith('/groups'):
            raise _http_error(400, {'error': {'code': 'PowerBIEntityAlreadyExists'}})
        if method == 'GET' and url.endswith('/groups'):
            return _resp({'value': [{'id': 'existing-ws', 'name': 'Ventas_semantic_dev'}]})
        raise AssertionError(f"unexpected call {method} {url}")

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        workspace = client.create_workspace("Ventas_semantic_dev")

    assert workspace['id'] == 'existing-ws'


def test_create_workspace_propagates_other_errors(client):
    def side_effect(method, url, **kwargs):
        raise _http_error(500)

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        with pytest.raises(requests.exceptions.HTTPError):
            client.create_workspace("Ventas_semantic_dev")


def test_list_capacities(client):
    def side_effect(method, url, **kwargs):
        assert url.endswith('/capacities')
        return _resp({'value': [{'id': 'cap-1', 'displayName': 'Cap A', 'sku': 'F2', 'state': 'Active'}]})

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        capacities = client.list_capacities()

    assert len(capacities) == 1
    assert capacities[0]['displayName'] == 'Cap A'
