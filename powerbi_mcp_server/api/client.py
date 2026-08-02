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
    
    def create_item(self, workspace_id: str, item_type: str, display_name: str, definition: Dict) -> Dict:
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
        self, workspace_id: str, item_type: str, display_name: str, definition: Dict
    ) -> tuple:
        """
        Create or update a Fabric item by display name.

        Returns:
            (item_dict, created: bool) — created=True if new, False if updated in-place
        """
        items = self.list_workspace_items(workspace_id, item_type)
        existing = next((i for i in items if i['displayName'] == display_name), None)

        if existing:
            self.update_item_definition(workspace_id, existing['id'], definition)
            logger.info(f"Upserted (updated) {item_type}: {display_name}")
            return existing, False
        else:
            item = self.create_item(workspace_id, item_type, display_name, definition)
            logger.info(f"Upserted (created) {item_type}: {display_name}")
            return item, True
