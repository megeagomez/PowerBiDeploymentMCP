from unittest.mock import MagicMock, patch

import pytest
import requests

from powerbi_mcp_server.api.client import PowerBIClient


def _resp(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _http_error(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "conflict"
    return requests.exceptions.HTTPError(response=resp)


@pytest.fixture
def client() -> PowerBIClient:
    return PowerBIClient("fake-token")


def test_resolve_or_create_folder_path_empty_short_circuits(client):
    with patch("powerbi_mcp_server.api.client.request_with_retry") as mock_req:
        assert client.resolve_or_create_folder_path("ws1", None) is None
        assert client.resolve_or_create_folder_path("ws1", "") is None
        assert client.resolve_or_create_folder_path("ws1", "   ") is None
        mock_req.assert_not_called()


def test_resolve_or_create_folder_path_creates_missing_single_segment(client):
    def side_effect(method, url, **kwargs):
        if method == 'GET':
            return _resp({'value': []})
        if method == 'POST':
            payload = kwargs['json']
            return _resp({'id': 'folder-a', 'displayName': payload['displayName'], 'parentFolderId': None})
        raise AssertionError(f"unexpected method {method}")

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        folder_id = client.resolve_or_create_folder_path("ws1", "Ventas")

    assert folder_id == 'folder-a'


def test_resolve_or_create_folder_path_reuses_existing_without_posting(client):
    def side_effect(method, url, **kwargs):
        if method == 'GET':
            return _resp({'value': [{'id': 'folder-existing', 'displayName': 'Ventas', 'parentFolderId': None}]})
        raise AssertionError("should not POST when the folder is already listed")

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        folder_id = client.resolve_or_create_folder_path("ws1", "Ventas")

    assert folder_id == 'folder-existing'


def test_resolve_or_create_folder_path_nested_segments(client):
    created = []

    def side_effect(method, url, **kwargs):
        if method == 'GET':
            return _resp({'value': []})
        if method == 'POST':
            payload = kwargs['json']
            created.append(payload)
            folder_id = f"folder-{len(created)}"
            return _resp({'id': folder_id, 'displayName': payload['displayName'],
                           'parentFolderId': payload.get('parentFolderId')})
        raise AssertionError(f"unexpected method {method}")

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        folder_id = client.resolve_or_create_folder_path("ws1", "Ventas/Modelos")

    assert len(created) == 2
    assert created[0]['displayName'] == 'Ventas'
    assert 'parentFolderId' not in created[0]
    assert created[1]['displayName'] == 'Modelos'
    assert created[1]['parentFolderId'] == 'folder-1'
    assert folder_id == 'folder-2'


def test_create_folder_reuses_existing_on_409_conflict(client):
    def side_effect(method, url, **kwargs):
        if method == 'POST':
            raise _http_error(409)
        if method == 'GET':
            return _resp({'value': [{'id': 'folder-existing', 'displayName': 'Ventas', 'parentFolderId': None}]})
        raise AssertionError(f"unexpected method {method}")

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        folder = client.create_folder("ws1", "Ventas", parent_folder_id=None)

    assert folder['id'] == 'folder-existing'


def test_create_folder_propagates_non_409_errors(client):
    def side_effect(method, url, **kwargs):
        raise _http_error(500)

    with patch("powerbi_mcp_server.api.client.request_with_retry", side_effect=side_effect):
        with pytest.raises(requests.exceptions.HTTPError):
            client.create_folder("ws1", "Ventas")


def test_upsert_item_moves_existing_item_when_folder_id_given(client):
    with patch.object(client, 'list_workspace_items', return_value=[{'id': 'existing-id', 'displayName': 'ModeloY'}]), \
         patch.object(client, 'update_item_definition') as mock_update, \
         patch.object(client, 'move_item') as mock_move:
        item, created = client.upsert_item("ws1", "SemanticModel", "ModeloY", {"parts": []}, folder_id="folder-x")

    assert created is False
    mock_update.assert_called_once()
    mock_move.assert_called_once_with("ws1", "existing-id", "folder-x")


def test_upsert_item_does_not_move_when_no_folder_id(client):
    with patch.object(client, 'list_workspace_items', return_value=[{'id': 'existing-id', 'displayName': 'ModeloY'}]), \
         patch.object(client, 'update_item_definition'), \
         patch.object(client, 'move_item') as mock_move:
        client.upsert_item("ws1", "SemanticModel", "ModeloY", {"parts": []})

    mock_move.assert_not_called()


def test_upsert_item_creates_with_folder_id(client):
    with patch.object(client, 'list_workspace_items', return_value=[]), \
         patch.object(client, 'create_item', return_value={'id': 'new-id'}) as mock_create:
        item, created = client.upsert_item("ws1", "SemanticModel", "ModeloY", {"parts": []}, folder_id="folder-x")

    assert created is True
    mock_create.assert_called_once_with("ws1", "SemanticModel", "ModeloY", {"parts": []}, folder_id="folder-x")
