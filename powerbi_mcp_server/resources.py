"""
MCP Resources

Implements resources for the Power BI MCP server that expose
server state, configuration, and data to clients.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResourceProviders:
    """Provides MCP resources for Power BI deployment server"""
    
    def __init__(self, metadata_manager, auth_manager=None):
        self.metadata = metadata_manager
        self.auth = auth_manager
    
    def get_server_config(self) -> Dict[str, Any]:
        """
        Get server configuration resource
        
        Returns current server configuration including paths,
        versioning settings, and environment variables.
        """
        db_path = self.metadata.db.db_path if hasattr(self.metadata, 'db') else None
        
        config = {
            'server_name': 'powerbi-mcp-deployment',
            'version': '0.1.0',
            'database': {
                'path': str(db_path) if db_path else 'Unknown',
                'schema_version': self.metadata.db.SCHEMA_VERSION if hasattr(self.metadata, 'db') else 1
            },
            'cache': {
                'directory': os.getenv('POWERBI_MCP_CACHE_DIR', str(Path.home() / '.powerbi-mcp-deployment' / 'cache'))
            },
            'versioning': {
                'enabled': os.getenv('POWERBI_MCP_VERSIONING_ENABLED', 'auto'),
                'format': os.getenv('POWERBI_MCP_VERSION_FORMAT', '%Y%m%d_%H%M%S')
            },
            'logging': {
                'level': os.getenv('POWERBI_MCP_LOG_LEVEL', 'INFO')
            },
            'environment': {
                'python_version': os.sys.version,
                'platform': os.sys.platform
            }
        }
        
        logger.info("Generated server config resource")
        return config
    
    def get_auth_status(self) -> Dict[str, Any]:
        """
        Get authentication status resource
        
        Returns current authentication state without sensitive data.
        """
        if not self.auth:
            return {
                'authenticated': False,
                'message': 'Authentication manager not initialized'
            }
        
        try:
            tokens = self.auth.get_tokens()
            is_authenticated = tokens is not None and 'powerbi' in tokens
            
            status = {
                'authenticated': is_authenticated,
                'timestamp': datetime.now().isoformat()
            }
            
            if is_authenticated:
                # Try to get user info without exposing sensitive data
                status['status'] = 'active'
                status['message'] = 'Successfully authenticated'
            else:
                status['status'] = 'not_authenticated'
                status['message'] = 'No valid authentication tokens found'
            
            logger.info(f"Generated auth status resource: authenticated={is_authenticated}")
            return status
            
        except Exception as e:
            logger.warning(f"Error getting auth status: {e}")
            return {
                'authenticated': False,
                'status': 'error',
                'message': str(e)
            }
    
    def get_metadata_stats(self) -> Dict[str, Any]:
        """
        Get metadata statistics resource
        
        Returns database statistics and health information.
        """
        try:
            stats = self.metadata.db.get_deployment_stats()
            
            result = {
                'database_health': 'healthy',
                'statistics': stats,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info("Generated metadata stats resource")
            return result
            
        except Exception as e:
            logger.error(f"Error getting metadata stats: {e}")
            return {
                'database_health': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_recent_deployments(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent deployments resource
        
        Returns the most recent upload operations.
        """
        try:
            self.metadata.db.connect()
            
            query = """
                SELECT 
                    artifact_name,
                    artifact_type,
                    workspace_name,
                    upload_timestamp,
                    operation_type,
                    asset_id
                FROM uploads
                ORDER BY upload_timestamp DESC
                LIMIT ?
            """
            
            result = self.metadata.db.conn.execute(query, [limit]).fetchall()
            columns = [desc[0] for desc in self.metadata.db.conn.description]
            deployments = [dict(zip(columns, row)) for row in result]
            
            # Convert timestamps to strings
            for deployment in deployments:
                if 'upload_timestamp' in deployment:
                    deployment['upload_timestamp'] = str(deployment['upload_timestamp'])
            
            logger.info(f"Generated recent deployments resource: {len(deployments)} entries")
            return deployments
            
        except Exception as e:
            logger.error(f"Error getting recent deployments: {e}")
            return []
    
    def get_workspace_summary(self) -> List[Dict[str, Any]]:
        """
        Get workspace summary resource
        
        Returns cached summary of accessible workspaces and their contents.
        """
        try:
            self.metadata.db.connect()
            
            # Get unique workspaces from uploads and downloads
            query = """
                SELECT DISTINCT
                    workspace_id,
                    workspace_name,
                    COUNT(*) as deployment_count,
                    MAX(upload_timestamp) as last_deployment
                FROM uploads
                GROUP BY workspace_id, workspace_name
                ORDER BY last_deployment DESC
            """
            
            result = self.metadata.db.conn.execute(query).fetchall()
            columns = [desc[0] for desc in self.metadata.db.conn.description]
            workspaces = [dict(zip(columns, row)) for row in result]
            
            # Convert timestamps
            for workspace in workspaces:
                if 'last_deployment' in workspace:
                    workspace['last_deployment'] = str(workspace['last_deployment'])
            
            logger.info(f"Generated workspace summary resource: {len(workspaces)} workspaces")
            return workspaces
            
        except Exception as e:
            logger.error(f"Error getting workspace summary: {e}")
            return []
    
    def get_deployment_history(self, workspace_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get deployment history for a specific workspace
        
        Args:
            workspace_name: Name of the workspace
            limit: Maximum number of records to return
        
        Returns:
            List of deployment records
        """
        try:
            self.metadata.db.connect()
            
            query = """
                SELECT 
                    artifact_name,
                    artifact_type,
                    workspace_name,
                    upload_timestamp,
                    operation_type,
                    asset_id,
                    source_file_path
                FROM uploads
                WHERE workspace_name = ?
                ORDER BY upload_timestamp DESC
                LIMIT ?
            """
            
            result = self.metadata.db.conn.execute(query, [workspace_name, limit]).fetchall()
            columns = [desc[0] for desc in self.metadata.db.conn.description]
            history = [dict(zip(columns, row)) for row in result]
            
            # Convert timestamps
            for record in history:
                if 'upload_timestamp' in record:
                    record['upload_timestamp'] = str(record['upload_timestamp'])
            
            logger.info(f"Generated deployment history for {workspace_name}: {len(history)} entries")
            return history
            
        except Exception as e:
            logger.error(f"Error getting deployment history for {workspace_name}: {e}")
            return []
    
    def get_deployment_configs(self) -> Dict[str, Any]:
        """
        Get deployment configurations resource
        
        Returns all deployment profiles and configured mappings.
        """
        try:
            profiles = self.metadata.db.list_deployment_profiles()
            semantic_models = self.metadata.db.list_semantic_model_configs()
            reports = self.metadata.db.list_report_configs()
            
            result = {
                'profiles': profiles,
                'semantic_models': semantic_models,
                'reports': reports,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Generated deployment configs resource: {len(profiles)} profiles, "
                       f"{len(semantic_models)} models, {len(reports)} reports")
            return result
            
        except Exception as e:
            logger.error(f"Error getting deployment configs: {e}")
            return {
                'profiles': [],
                'semantic_models': [],
                'reports': [],
                'error': str(e)
            }


# Resource URI templates
RESOURCE_TEMPLATES = {
    'server-config': {
        'uri': 'config://server',
        'name': 'Server Configuration',
        'description': 'Current MCP server configuration and settings',
        'mimeType': 'application/json'
    },
    'auth-status': {
        'uri': 'auth://status',
        'name': 'Authentication Status',
        'description': 'Current authentication state (no sensitive data)',
        'mimeType': 'application/json'
    },
    'metadata-stats': {
        'uri': 'metadata://stats',
        'name': 'Metadata Statistics',
        'description': 'Database statistics and health information',
        'mimeType': 'application/json'
    },
    'recent-deployments': {
        'uri': 'deployments://recent',
        'name': 'Recent Deployments',
        'description': 'Last 10 upload operations to Power BI',
        'mimeType': 'application/json'
    },
    'workspace-summary': {
        'uri': 'workspaces://summary',
        'name': 'Workspace Summary',
        'description': 'Summary of workspaces with deployment history',
        'mimeType': 'application/json'
    },
    'deployment-history': {
        'uri': 'deployments://{workspace_name}',
        'name': 'Deployment History',
        'description': 'Complete deployment history for a specific workspace',
        'mimeType': 'application/json'
    },
    'deployment-configs': {
        'uri': 'config://deployments',
        'name': 'Deployment Configurations',
        'description': 'All deployment profiles and artifact mappings',
        'mimeType': 'application/json'
    }
}
