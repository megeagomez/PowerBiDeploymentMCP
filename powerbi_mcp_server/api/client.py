"""
Power BI REST API Client

Wraps Power BI and Fabric API endpoints with authentication and error handling.
"""

import logging
import time
from typing import Callable, Dict, List, Optional, Union

import requests

from .http_utils import request_with_retry, APIError, translate_api_error

logger = logging.getLogger(__name__)


class PowerBIClient:
    """
    Client for Power BI REST API and Fabric API
    """
    
    # API Base URLs
    POWERBI_BASE_URL = "https://api.powerbi.com/v1.0/myorg"
    FABRIC_BASE_URL = "https://api.fabric.microsoft.com/v1"
    
    def __init__(self, token_or_provider: Union[str, Callable[[], Optional[str]]]):
        """
        Initialize the Power BI API client

        Args:
            token_or_provider: Bearer token string, or a zero-arg callable that
                returns the current token. Prefer the callable: headers are built
                per-request, so a token refreshed on disk is picked up without
                recreating the client (avoids 401s after token expiry).
        """
        if callable(token_or_provider):
            self._token_provider = token_or_provider
        else:
            self._token_provider = lambda: token_or_provider
        logger.info("Power BI API client initialized")

    @property
    def access_token(self) -> Optional[str]:
        return self._token_provider()

    @property
    def headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def _log_request(self, method: str, url: str, **kwargs):
        """Log API request details"""
        logger.debug(f"API Request: {method} {url}")
        if 'json' in kwargs:
            logger.debug(f"Request body: {kwargs['json']}")
    
    def _handle_error(self, error: Exception, operation: str) -> None:
        """
        Handle and log API errors
        
        Args:
            error: Exception that occurred
            operation: Description of the operation that failed
        """
        user_message = translate_api_error(error)
        logger.error(f"{operation} failed: {error}")
        logger.error(f"User message: {user_message}")
        
        if isinstance(error, requests.exceptions.HTTPError) and hasattr(error, 'response'):
            logger.error(f"Response body: {error.response.text}")
    
    # Workspace operations
    
    def list_workspaces(self, filter_query: Optional[str] = None) -> List[Dict]:
        """
        List all workspaces accessible to the user
        
        Args:
            filter_query: Optional OData filter query
            
        Returns:
            List of workspace dictionaries
        """
        url = f"{self.POWERBI_BASE_URL}/groups"
        params = {}
        if filter_query:
            params['$filter'] = filter_query
        
        try:
            self._log_request('GET', url, params=params)
            response = request_with_retry('GET', url, headers=self.headers, params=params)
            data = response.json()
            workspaces = data.get('value', [])
            logger.info(f"Retrieved {len(workspaces)} workspaces")
            return workspaces
        except Exception as e:
            self._handle_error(e, "List workspaces")
            raise
    
    def get_workspace_by_name(self, workspace_name: str) -> Optional[Dict]:
        """
        Find a workspace by exact name match
        
        Args:
            workspace_name: Name of the workspace
            
        Returns:
            Workspace dictionary if found, None otherwise
        """
        try:
            # OData string literals escape single quotes by doubling them
            escaped_name = workspace_name.replace("'", "''")
            filter_query = f"name eq '{escaped_name}'"
            workspaces = self.list_workspaces(filter_query=filter_query)
            
            for workspace in workspaces:
                if workspace.get('name') == workspace_name:
                    logger.info(f"Found workspace: {workspace_name} (ID: {workspace.get('id')})")
                    return workspace
            
            logger.warning(f"Workspace not found: {workspace_name}")
            return None
        except Exception as e:
            self._handle_error(e, f"Get workspace by name: {workspace_name}")
            raise

    def create_workspace(
        self, workspace_name: str, description: Optional[str] = None, capacity_id: Optional[str] = None
    ) -> Dict:
        """
        Create a new Power BI workspace. If a workspace with that exact name
        already exists, reuses it instead of failing (mirrors the
        already-proven behaviour in powerbi_object_manager.py's
        create_workspace/create_folder).

        Args:
            capacity_id: Optional Fabric capacity ID to assign the workspace to.
                If omitted, the workspace is created without a capacity
                (still valid on many tenants; can be assigned later).

        Returns:
            Workspace dict with at least 'id' and 'name'.
        """
        url = f"{self.POWERBI_BASE_URL}/groups"
        payload = {'name': workspace_name}

        try:
            self._log_request('POST', url, json=payload)
            response = request_with_retry('POST', url, headers=self.headers, json=payload)
            workspace = response.json()
            logger.info(f"Created workspace: {workspace_name} (ID: {workspace.get('id')})")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (400, 409) and self._is_duplicate_workspace_error(e.response):
                existing = self.get_workspace_by_name(workspace_name)
                if existing:
                    logger.info(f"Workspace already exists, reusing: {workspace_name} (ID: {existing.get('id')})")
                    return existing
            self._handle_error(e, f"Create workspace: {workspace_name}")
            raise
        except Exception as e:
            self._handle_error(e, f"Create workspace: {workspace_name}")
            raise

        if description:
            # Best-effort: workspace description isn't settable at creation time
            # via this endpoint; not critical enough to fail workspace creation over.
            pass

        if capacity_id:
            self._assign_workspace_to_capacity(workspace['id'], capacity_id)

        return workspace

    def _assign_workspace_to_capacity(self, workspace_id: str, capacity_id: str) -> None:
        url = f"{self.POWERBI_BASE_URL}/groups/{workspace_id}/AssignToCapacity"
        payload = {'capacityId': capacity_id}
        try:
            self._log_request('POST', url, json=payload)
            request_with_retry('POST', url, headers=self.headers, json=payload)
            logger.info(f"Assigned workspace {workspace_id} to capacity {capacity_id}")
        except Exception as e:
            self._handle_error(e, f"Assign workspace to capacity: {workspace_id}")
            raise

    @staticmethod
    def _is_duplicate_workspace_error(response: requests.Response) -> bool:
        if response.status_code == 409:
            return True
        try:
            body = response.json()
            code = body.get('error', {}).get('code', '') or body.get('errorCode', '')
            return 'AlreadyExists' in code or 'AlreadyInUse' in code
        except Exception:
            return False

    def list_capacities(self) -> List[Dict]:
        """List Fabric capacities available to the user (id, displayName, sku, region, state)."""
        url = f"{self.FABRIC_BASE_URL}/capacities"
        try:
            self._log_request('GET', url)
            response = request_with_retry('GET', url, headers=self.headers)
            capacities = response.json().get('value', [])
            logger.info(f"Retrieved {len(capacities)} capacities")
            return capacities
        except Exception as e:
            self._handle_error(e, "List capacities")
            raise

    def list_workspace_items(
        self,
        workspace_id: str,
        item_type: Optional[str] = None
    ) -> List[Dict]:
        """
        List items in a workspace with optional type filtering
        
        Args:
            workspace_id: ID of the workspace
            item_type: Optional item type filter (e.g., 'SemanticModel', 'Report')
            
        Returns:
            List of item dictionaries
        """
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/items"
        params = {}
        if item_type:
            params['type'] = item_type
        
        items = []
        try:
            while url:
                self._log_request('GET', url, params=params)
                response = request_with_retry('GET', url, headers=self.headers, params=params)
                data = response.json()
                
                items.extend(data.get('value', []))
                url = data.get('continuationUri')
                params = {}  # Clear params for continuation
            
            logger.info(f"Retrieved {len(items)} items from workspace {workspace_id}")
            return items
        except Exception as e:
            self._handle_error(e, f"List workspace items: {workspace_id}")
            raise
    
    def get_workspace_details(self, workspace_id: str) -> Dict:
        """
        Get detailed information about a workspace
        
        Args:
            workspace_id: ID of the workspace
            
        Returns:
            Workspace details dictionary
        """
        url = f"{self.POWERBI_BASE_URL}/groups/{workspace_id}"
        
        try:
            self._log_request('GET', url)
            response = request_with_retry('GET', url, headers=self.headers)
            workspace = response.json()
            logger.info(f"Retrieved details for workspace: {workspace.get('name')}")
            return workspace
        except Exception as e:
            self._handle_error(e, f"Get workspace details: {workspace_id}")
            raise
    
    def rebind_report(self, workspace_id: str, report_id: str, dataset_id: str) -> None:
        """
        Rebind a report to a different dataset (semantic model).

        The target dataset can live in a different workspace than the report,
        as long as the caller has Build permission on it.

        Args:
            workspace_id: ID of the workspace containing the report
            report_id: ID of the report to rebind
            dataset_id: ID of the dataset/semantic model to bind to
        """
        url = f"{self.POWERBI_BASE_URL}/groups/{workspace_id}/reports/{report_id}/Rebind"
        payload = {'datasetId': dataset_id}

        try:
            self._log_request('POST', url, json=payload)
            request_with_retry('POST', url, headers=self.headers, json=payload)
            logger.info(f"Rebound report {report_id} to dataset {dataset_id}")
        except Exception as e:
            self._handle_error(e, f"Rebind report {report_id} to dataset {dataset_id}")
            raise

    # Semantic Model operations

    # NOTE: there is no dataset-level PBIX export endpoint in the Power BI REST
    # API (export is report-level only), so semantic models download as PBIP.

    def _poll_lro_operation(self, location_url: str, max_wait_seconds: int = 600) -> Dict:
        """Poll a Fabric Long Running Operation until it succeeds or fails.

        Honors the Retry-After header between polls (falls back to 2s).
        """
        start = time.time()
        while True:
            if time.time() - start > max_wait_seconds:
                raise APIError(f"LRO operation timed out after {max_wait_seconds}s: {location_url}")

            response = request_with_retry('GET', location_url, headers=self.headers)
            status_data = response.json()

            status = status_data.get('status', '')
            logger.debug(f"LRO status: {status}")

            if status == 'Succeeded':
                result_url = location_url.rstrip('/') + '/result'
                # Some operations (e.g. updateDefinition) have no result payload
                # and answer 4xx here — treat any error as an empty result.
                result_response = requests.get(result_url, headers=self.headers)
                if result_response.status_code == 204 or not result_response.content:
                    return {}
                if not result_response.ok:
                    return {}
                try:
                    return result_response.json()
                except ValueError:
                    return {}
            elif status in ('Failed', 'Cancelled'):
                error_info = status_data.get('error', {})
                raise APIError(f"LRO operation {status}: {error_info.get('message', 'Unknown error')}")

            retry_after = response.headers.get('Retry-After')
            try:
                delay = float(retry_after) if retry_after else 2.0
            except (TypeError, ValueError):
                delay = 2.0
            time.sleep(min(delay, 30.0))

    def get_item_definition(self, workspace_id: str, item_id: str) -> Dict:
        """
        Get definition of a Fabric item (for PBIP/PBIR formats).
        Handles async (202 LRO) responses automatically.

        Returns:
            Definition dictionary with parts
        """
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/items/{item_id}/getDefinition"

        try:
            self._log_request('POST', url)
            response = request_with_retry('POST', url, headers=self.headers)

            if response.status_code == 202:
                location = response.headers.get('Location')
                if not location:
                    raise APIError("getDefinition returned 202 but no Location header found")
                logger.info(f"getDefinition is async, polling LRO: {location}")
                definition = self._poll_lro_operation(location)
            else:
                definition = response.json()

            raw_def = definition.get('definition') or {}
            num_parts = len(raw_def.get('parts', []))
            logger.info(f"Retrieved item definition with {num_parts} parts")
            return definition
        except Exception as e:
            self._handle_error(e, f"Get item definition: {item_id}")
            raise
    
    def import_pbix(self, workspace_id: str, file_path: str, dataset_name: str) -> Dict:
        """
        Import a PBIX file to a workspace
        
        Args:
            workspace_id: ID of the workspace
            file_path: Path to the PBIX file
            dataset_name: Name for the imported dataset
            
        Returns:
            Import result dictionary
        """
        url = f"{self.POWERBI_BASE_URL}/groups/{workspace_id}/imports"
        params = {'datasetDisplayName': dataset_name}
        
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (dataset_name, f, 'application/octet-stream')}
                headers = {'Authorization': f'Bearer {self.access_token}'}
                
                self._log_request('POST', url, params=params)
                response = request_with_retry(
                    'POST', url, headers=headers, files=files, params=params
                )
                result = response.json()
                logger.info(f"Imported PBIX: {dataset_name}")
                return result
        except Exception as e:
            self._handle_error(e, f"Import PBIX: {dataset_name}")
            raise
    
    def create_item(
        self, workspace_id: str, item_type: str, display_name: str, definition: Dict,
        folder_id: Optional[str] = None
    ) -> Dict:
        """
        Create a new Fabric item with definition via POST /items.
        Handles LRO (202 Accepted) automatically.
        """
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/items"

        payload = {
            'displayName': display_name,
            'type': item_type,
            'definition': definition,
        }
        if folder_id:
            payload['folderId'] = folder_id

        try:
            self._log_request('POST', url, json=payload)
            response = request_with_retry('POST', url, headers=self.headers, json=payload)

            if response.status_code == 202:
                location = response.headers.get('Location')
                if not location:
                    raise APIError("createItem returned 202 but no Location header found")
                logger.info(f"createItem is async, polling LRO: {location}")
                item = self._poll_lro_operation(location)
            else:
                item = response.json()

            logger.info(f"Created {item_type}: {display_name} (ID: {item.get('id')})")
            return item
        except Exception as e:
            self._handle_error(e, f"Create {item_type}: {display_name}")
            raise

    def update_item_definition(self, workspace_id: str, item_id: str, definition: Dict) -> None:
        """
        Update an existing item's definition via POST /updateDefinition.
        Handles LRO (202 Accepted) automatically.
        """
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/items/{item_id}/updateDefinition"
        payload = {'definition': definition}

        try:
            self._log_request('POST', url, json=payload)
            response = request_with_retry('POST', url, headers=self.headers, json=payload)

            if response.status_code == 202:
                location = response.headers.get('Location')
                if location:
                    logger.info(f"updateDefinition is async, polling LRO: {location}")
                    self._poll_lro_operation(location)

            logger.info(f"Updated item definition: {item_id}")
        except Exception as e:
            self._handle_error(e, f"Update item definition: {item_id}")
            raise

    def upsert_item(
        self, workspace_id: str, item_type: str, display_name: str, definition: Dict,
        folder_id: Optional[str] = None
    ) -> tuple:
        """
        Create or update a Fabric item by display name.

        If folder_id is given: a newly created item is placed there directly;
        an item that already existed gets relocated there via move_item (so a
        re-upload after changing the configured folder actually moves it,
        instead of leaving it wherever it was created originally).

        Returns:
            (item_dict, created: bool) — created=True if new, False if updated in-place
        """
        items = self.list_workspace_items(workspace_id, item_type)
        existing = next((i for i in items if i['displayName'] == display_name), None)

        if existing:
            self.update_item_definition(workspace_id, existing['id'], definition)
            if folder_id:
                self.move_item(workspace_id, existing['id'], folder_id)
            logger.info(f"Upserted (updated) {item_type}: {display_name}")
            return existing, False
        else:
            item = self.create_item(workspace_id, item_type, display_name, definition, folder_id=folder_id)
            logger.info(f"Upserted (created) {item_type}: {display_name}")
            return item, True

    # Folder operations

    def list_folders(self, workspace_id: str) -> List[Dict]:
        """
        List all folders in a workspace (paginated via continuationUri, same
        pattern as list_workspace_items).
        """
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/folders"
        folders = []
        try:
            while url:
                self._log_request('GET', url)
                response = request_with_retry('GET', url, headers=self.headers)
                data = response.json()
                folders.extend(data.get('value', []))
                url = data.get('continuationUri')

            logger.info(f"Retrieved {len(folders)} folders from workspace {workspace_id}")
            return folders
        except Exception as e:
            self._handle_error(e, f"List folders: {workspace_id}")
            raise

    def create_folder(
        self, workspace_id: str, display_name: str, parent_folder_id: Optional[str] = None
    ) -> Dict:
        """
        Create a folder in a workspace. If a folder with that name already
        exists under the same parent (API returns 409), reuse it instead of
        failing — mirrors the behaviour already proven in
        powerbi_object_manager.py's create_folder/_find_folder_by_name.
        """
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/folders"
        payload = {'displayName': display_name}
        if parent_folder_id:
            payload['parentFolderId'] = parent_folder_id

        try:
            self._log_request('POST', url, json=payload)
            response = request_with_retry('POST', url, headers=self.headers, json=payload)
            folder = response.json()
            logger.info(f"Created folder: {display_name} (ID: {folder.get('id')})")
            return folder
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                existing = next(
                    (
                        f for f in self.list_folders(workspace_id)
                        if f.get('displayName') == display_name and f.get('parentFolderId') == parent_folder_id
                    ),
                    None
                )
                if existing:
                    logger.info(f"Folder already exists, reusing: {display_name} (ID: {existing.get('id')})")
                    return existing
            self._handle_error(e, f"Create folder: {display_name}")
            raise
        except Exception as e:
            self._handle_error(e, f"Create folder: {display_name}")
            raise

    def resolve_or_create_folder_path(self, workspace_id: str, folder_path: Optional[str]) -> Optional[str]:
        """
        Resolve a '/'-separated folder path to the leaf folder's ID, creating
        any missing segment along the way. Returns None (no API calls) if
        folder_path is empty/None.
        """
        if not folder_path:
            return None

        segments = [s.strip() for s in folder_path.split('/') if s.strip()]
        if not segments:
            return None

        existing_folders = self.list_folders(workspace_id)
        parent_id = None
        for segment in segments:
            match = next(
                (
                    f for f in existing_folders
                    if f.get('displayName') == segment and f.get('parentFolderId') == parent_id
                ),
                None
            )
            if match:
                parent_id = match['id']
                continue

            folder = self.create_folder(workspace_id, segment, parent_folder_id=parent_id)
            parent_id = folder['id']
            existing_folders.append(folder)

        return parent_id

    def move_item(self, workspace_id: str, item_id: str, folder_id: Optional[str]) -> None:
        """Move an existing item to a different folder (or to the workspace root if folder_id is None)."""
        url = f"{self.FABRIC_BASE_URL}/workspaces/{workspace_id}/items/{item_id}/move"
        payload = {'targetFolderId': folder_id}

        try:
            self._log_request('POST', url, json=payload)
            request_with_retry('POST', url, headers=self.headers, json=payload)
            logger.info(f"Moved item {item_id} to folder {folder_id}")
        except Exception as e:
            self._handle_error(e, f"Move item: {item_id}")
            raise
