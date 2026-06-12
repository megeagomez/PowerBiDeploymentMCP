"""
MCP Tool Handlers

Implements handlers for all MCP tools exposed by the Power BI MCP server.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server

from powerbi_mcp_server.api import PowerBIClient
from powerbi_mcp_server.api.semantic_models import SemanticModelOperations
from powerbi_mcp_server.api.reports import ReportOperations
from powerbi_mcp_server.auth import get_authenticator
from powerbi_mcp_server.auth.authenticator import AuthenticationRequired
from powerbi_mcp_server.metadata import MetadataManager
from powerbi_mcp_server.metadata.deployment_config import DeploymentConfigManager

logger = logging.getLogger(__name__)


class ToolHandlers:
    """MCP Tool handlers for Power BI operations"""
    
    def __init__(self, metadata_manager: MetadataManager):
        self.metadata = metadata_manager
        self.deploy_config = DeploymentConfigManager(metadata_manager.database)
        self._client: Optional[PowerBIClient] = None
        self._semantic_models: Optional[SemanticModelOperations] = None
        self._reports: Optional[ReportOperations] = None
    
    async def authenticate(self, arguments: Dict[str, Any]) -> Dict:
        """Start Device Flow authentication and return the login URL/code to the user."""
        auth = get_authenticator()
        message = await auth.start_device_flow()
        return {"success": True, "message": message}

    async def _ensure_authenticated(self) -> PowerBIClient:
        """Return authenticated client or raise AuthenticationRequired."""
        auth = get_authenticator()
        await auth.ensure_authenticated()  # raises AuthenticationRequired if no token

        if self._client is None:
            tokens = auth.get_tokens()
            self._client = PowerBIClient(tokens['powerbi'])
            self._semantic_models = SemanticModelOperations(self._client, self.metadata)
            self._reports = ReportOperations(self._client, self.metadata)

        return self._client
    
    async def list_workspaces(self, arguments: Dict[str, Any]) -> List[Dict]:
        """List all accessible workspaces"""
        client = await self._ensure_authenticated()
        
        filter_query = arguments.get('filter')
        workspaces = client.list_workspaces(filter_query=filter_query)
        
        logger.info(f"Retrieved {len(workspaces)} workspaces")
        return {
            'workspaces': workspaces,
            'count': len(workspaces)
        }
    
    async def get_workspace_contents(self, arguments: Dict[str, Any]) -> Dict:
        """Get contents of a specific workspace"""
        client = await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        item_type = arguments.get('item_type')
        
        # Find workspace
        workspace = client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        
        workspace_id = workspace['id']
        
        # Get items
        items = client.list_workspace_items(workspace_id, item_type=item_type)
        
        logger.info(f"Retrieved {len(items)} items from workspace {workspace_name}")
        return {
            'workspace': workspace,
            'items': items,
            'count': len(items)
        }
    
    async def download_semantic_model(self, arguments: Dict[str, Any]) -> Dict:
        """Download a semantic model"""
        await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        dataset_name = arguments['dataset_name']
        target_path = Path(arguments['target_path'])
        format = arguments.get('format')
        
        # Find workspace and dataset
        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        
        workspace_id = workspace['id']
        
        items = self._client.list_workspace_items(workspace_id, 'SemanticModel')
        dataset = next((item for item in items if item['displayName'] == dataset_name), None)
        if not dataset:
            raise ValueError(f"Modelo semántico no encontrado: {dataset_name}")
        
        dataset_id = dataset['id']
        
        # Auto-detect format if not specified
        if format is None:
            format = self._semantic_models.detect_format(target_path) or 'pbix'
        
        # Download
        auth = get_authenticator()
        user_info = auth.get_user_info()
        
        if format == 'pbix':
            result = await self._semantic_models.download_pbix(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                target_path=target_path,
                user_email=user_info.get('email')
            )
        else:  # pbip
            result = await self._semantic_models.download_pbip(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                target_dir=target_path,
                user_email=user_info.get('email')
            )
        
        return result
    
    async def upload_semantic_model(self, arguments: Dict[str, Any]) -> Dict:
        """Upload a semantic model"""
        await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        source_path = Path(arguments['source_path'])
        dataset_name = arguments.get('dataset_name')
        
        # Find workspace
        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        
        workspace_id = workspace['id']
        
        # Detect format
        format = self._semantic_models.detect_format(source_path)
        if format is None:
            raise ValueError(f"No se pudo detectar el formato del modelo semántico: {source_path}")
        
        # Upload
        auth = get_authenticator()
        user_info = auth.get_user_info()
        
        if format == 'pbix':
            result = await self._semantic_models.upload_pbix(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                file_path=source_path,
                dataset_name=dataset_name,
                user_email=user_info.get('email')
            )
        else:  # pbip
            result = await self._semantic_models.upload_pbip(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                directory_path=source_path,
                dataset_name=dataset_name,
                user_email=user_info.get('email')
            )
        
        return result
    
    async def download_report(self, arguments: Dict[str, Any]) -> Dict:
        """Download a report"""
        await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        report_name = arguments['report_name']
        target_path = Path(arguments['target_path'])
        format = arguments.get('format', 'pbir')
        
        # Find workspace and report
        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        
        workspace_id = workspace['id']
        
        items = self._client.list_workspace_items(workspace_id, 'Report')
        report = next((item for item in items if item['displayName'] == report_name), None)
        if not report:
            raise ValueError(f"Informe no encontrado: {report_name}")
        
        report_id = report['id']
        
        # Download
        auth = get_authenticator()
        user_info = auth.get_user_info()
        
        result = await self._reports.download_pbir(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            report_id=report_id,
            report_name=report_name,
            target_dir=target_path,
            user_email=user_info.get('email')
        )
        
        return result
    
    async def upload_report(self, arguments: Dict[str, Any]) -> Dict:
        """Upload a report"""
        await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        source_path = Path(arguments['source_path'])
        report_name = arguments.get('report_name')
        rebind_to_model = arguments.get('rebind_to_model')
        rebind_workspace_name = arguments.get('rebind_workspace_name')

        # Find workspace
        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")

        workspace_id = workspace['id']

        # Find semantic model if rebinding (optionally in a different workspace)
        semantic_model_id = None
        if rebind_to_model:
            model_workspace_id = workspace_id
            if rebind_workspace_name:
                model_workspace = self._client.get_workspace_by_name(rebind_workspace_name)
                if not model_workspace:
                    raise ValueError(f"Workspace no encontrado: {rebind_workspace_name}")
                model_workspace_id = model_workspace['id']

            models = self._reports.find_semantic_models_by_name(model_workspace_id, rebind_to_model)
            if not models:
                raise ValueError(f"Modelo semántico no encontrado para reenlace: {rebind_to_model}")
            semantic_model_id = models[0]['id']
        
        # Upload
        auth = get_authenticator()
        user_info = auth.get_user_info()
        
        result = await self._reports.upload_pbir(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            directory_path=source_path,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
            user_email=user_info.get('email')
        )
        
        return result

    async def rebind_report(self, arguments: Dict[str, Any]) -> Dict:
        """Rebind an existing report to a different semantic model, without re-uploading it.

        The target semantic model can live in a different workspace than the report.
        """
        await self._ensure_authenticated()

        workspace_name = arguments['workspace_name']
        report_name = arguments['report_name']
        target_model_name = arguments['target_model_name']
        target_model_workspace_name = arguments.get('target_model_workspace_name', workspace_name)

        # Find report's workspace
        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        workspace_id = workspace['id']

        # Find target model's workspace (may be the same)
        model_workspace_id = workspace_id
        if target_model_workspace_name != workspace_name:
            model_workspace = self._client.get_workspace_by_name(target_model_workspace_name)
            if not model_workspace:
                raise ValueError(f"Workspace no encontrado: {target_model_workspace_name}")
            model_workspace_id = model_workspace['id']

        models = self._reports.find_semantic_models_by_name(model_workspace_id, target_model_name)
        if not models:
            raise ValueError(f"Modelo semántico no encontrado para reenlace: {target_model_name}")
        semantic_model_id = models[0]['id']
        semantic_model_name = models[0]['displayName']

        auth = get_authenticator()
        user_info = auth.get_user_info()

        result = await self._reports.rebind_report(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
            semantic_model_name=semantic_model_name,
            semantic_model_workspace_name=target_model_workspace_name,
            user_email=user_info.get('email')
        )

        return result

    async def download_workspace(self, arguments: Dict[str, Any]) -> Dict:
        """Download all semantic models and reports from a workspace"""
        await self._ensure_authenticated()

        workspace_name = arguments['workspace_name']
        destination_path = Path(arguments['destination_path'])
        include_models = arguments.get('include_semantic_models', True)
        include_reports = arguments.get('include_reports', True)

        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")

        workspace_id = workspace['id']
        destination_path.mkdir(parents=True, exist_ok=True)

        auth = get_authenticator()
        user_info = auth.get_user_info()
        user_email = user_info.get('email')

        results = {'workspace': workspace_name, 'destination': str(destination_path),
                   'semantic_models': [], 'reports': [], 'errors': []}

        # Download semantic models
        if include_models:
            models = self._client.list_workspace_items(workspace_id, 'SemanticModel')
            logger.info(f"Downloading {len(models)} semantic models from {workspace_name}")
            for model in models:
                try:
                    result = await self._semantic_models.download_pbip(
                        workspace_id=workspace_id,
                        workspace_name=workspace_name,
                        dataset_id=model['id'],
                        dataset_name=model['displayName'],
                        target_dir=destination_path,
                        user_email=user_email
                    )
                    results['semantic_models'].append({
                        'name': model['displayName'],
                        'status': 'ok',
                        'parts': result['parts_count'],
                        'path': result['directory_path']
                    })
                except Exception as e:
                    logger.error(f"Failed to download model {model['displayName']}: {e}")
                    results['errors'].append({'type': 'SemanticModel', 'name': model['displayName'], 'error': str(e)})

        # Download reports
        if include_reports:
            reports = self._client.list_workspace_items(workspace_id, 'Report')
            logger.info(f"Downloading {len(reports)} reports from {workspace_name}")
            for report in reports:
                try:
                    result = await self._reports.download_pbir(
                        workspace_id=workspace_id,
                        workspace_name=workspace_name,
                        report_id=report['id'],
                        report_name=report['displayName'],
                        target_dir=destination_path,
                        user_email=user_email
                    )
                    results['reports'].append({
                        'name': report['displayName'],
                        'status': 'ok',
                        'parts': result['parts_count'],
                        'path': result['directory_path']
                    })
                except Exception as e:
                    logger.error(f"Failed to download report {report['displayName']}: {e}")
                    results['errors'].append({'type': 'Report', 'name': report['displayName'], 'error': str(e)})

        results['summary'] = {
            'models_ok': len(results['semantic_models']),
            'reports_ok': len(results['reports']),
            'errors': len(results['errors'])
        }
        logger.info(f"Workspace download complete: {results['summary']}")
        return results

    async def list_semantic_models(self, arguments: Dict[str, Any]) -> Dict:
        """List semantic models in a workspace"""
        client = await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        
        # Find workspace
        workspace = client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        
        workspace_id = workspace['id']
        
        # Get semantic models
        models = client.list_workspace_items(workspace_id, 'SemanticModel')
        
        logger.info(f"Retrieved {len(models)} semantic models from workspace {workspace_name}")
        return {
            'workspace': workspace,
            'semantic_models': models,
            'count': len(models)
        }
    
    async def query_version_history(self, arguments: Dict[str, Any]) -> Dict:
        """Query version history for an artifact"""
        artifact_name = arguments['artifact_name']
        artifact_type = arguments.get('artifact_type')
        
        history = self.metadata.get_version_history(artifact_name, artifact_type)
        
        logger.info(f"Retrieved {len(history)} version history entries for {artifact_name}")
        return {
            'artifact_name': artifact_name,
            'artifact_type': artifact_type,
            'history': history,
            'count': len(history)
        }
    
    async def query_deployments(self, arguments: Dict[str, Any]) -> Dict:
        """Query deployment history for a workspace"""
        client = await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        
        # Find workspace
        workspace = client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")
        
        workspace_id = workspace['id']
        
        deployments = self.metadata.get_workspace_deployments(workspace_id)
        
        logger.info(f"Retrieved {len(deployments)} deployments for workspace {workspace_name}")
        return {
            'workspace': workspace,
            'deployments': deployments,
            'count': len(deployments)
        }
    
    # ========== Deployment Configuration Handlers ==========
    
    async def configure_semantic_model_deployment(self, arguments: Dict[str, Any]) -> Dict:
        """Configure automatic deployment for a semantic model"""
        client = await self._ensure_authenticated()
        
        model_name = arguments['model_name']
        target_workspace_name = arguments['target_workspace_name']
        target_workspace_id = arguments.get('target_workspace_id')
        auto_deploy = arguments.get('auto_deploy', False)
        notes = arguments.get('notes')
        
        # Resolve workspace if ID not provided
        if not target_workspace_id:
            workspace = client.get_workspace_by_name(target_workspace_name)
            if workspace:
                target_workspace_id = workspace['id']
            else:
                logger.warning(f"Workspace {target_workspace_name} not found, saving name only")
                target_workspace_id = ''
        
        # Check if config already exists
        existing_config = self.deploy_config.db.get_semantic_model_config(model_name)

        if existing_config:
            # Update existing
            self.deploy_config.db.update_semantic_model_config(
                model_name=model_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                auto_deploy=auto_deploy,
                notes=notes
            )
            logger.info(f"Updated semantic model config: {model_name}")
            action = 'updated'
        else:
            # Create new
            config_id = self.deploy_config.db.create_semantic_model_config(
                model_name=model_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                auto_deploy=auto_deploy,
                notes=notes
            )
            logger.info(f"Created semantic model config: {model_name} (ID: {config_id})")
            action = 'created'
        
        return {
            'success': True,
            'action': action,
            'model_name': model_name,
            'target_workspace': target_workspace_name,
            'auto_deploy': auto_deploy,
            'message': f'Configuración {action} para {model_name} → {target_workspace_name}'
        }
    
    async def configure_report_deployment(self, arguments: Dict[str, Any]) -> Dict:
        """Configure automatic deployment for a report"""
        client = await self._ensure_authenticated()
        
        report_name = arguments['report_name']
        target_workspace_name = arguments['target_workspace_name']
        target_workspace_id = arguments.get('target_workspace_id')
        target_model_name = arguments.get('target_semantic_model_name')
        target_model_workspace_name = arguments.get('target_model_workspace_name', target_workspace_name)
        auto_deploy = arguments.get('auto_deploy', False)
        auto_rebind = arguments.get('auto_rebind', True)
        notes = arguments.get('notes')
        
        # Resolve workspace if ID not provided
        if not target_workspace_id:
            workspace = client.get_workspace_by_name(target_workspace_name)
            if workspace:
                target_workspace_id = workspace['id']
            else:
                logger.warning(f"Workspace {target_workspace_name} not found, saving name only")
                target_workspace_id = ''
        
        # Resolve model workspace if different
        target_model_workspace_id = None
        if target_model_workspace_name and target_model_workspace_name != target_workspace_name:
            model_workspace = client.get_workspace_by_name(target_model_workspace_name)
            if model_workspace:
                target_model_workspace_id = model_workspace['id']
        
        # Resolve semantic model ID if name provided
        target_model_id = None
        if target_model_name:
            model_ws_id = target_model_workspace_id or target_workspace_id
            if model_ws_id:
                items = client.list_workspace_items(model_ws_id, 'SemanticModel')
                model = next((item for item in items if item['displayName'] == target_model_name), None)
                if model:
                    target_model_id = model['id']
                else:
                    logger.warning(f"Semantic model {target_model_name} not found in workspace")
        
        # Check if config already exists
        existing_config = self.deploy_config.db.get_report_config(report_name)

        if existing_config:
            # Update existing
            self.deploy_config.db.update_report_config(
                report_name=report_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                target_semantic_model_name=target_model_name,
                target_model_workspace_name=target_model_workspace_name,
                auto_deploy=auto_deploy,
                auto_rebind=auto_rebind,
                notes=notes
            )
            logger.info(f"Updated report config: {report_name}")
            action = 'updated'
        else:
            # Create new
            config_id = self.deploy_config.db.create_report_config(
                report_name=report_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                target_semantic_model_id=target_model_id,
                target_semantic_model_name=target_model_name,
                target_model_workspace_id=target_model_workspace_id,
                target_model_workspace_name=target_model_workspace_name,
                auto_deploy=auto_deploy,
                auto_rebind=auto_rebind,
                notes=notes
            )
            logger.info(f"Created report config: {report_name} (ID: {config_id})")
            action = 'created'
        
        return {
            'success': True,
            'action': action,
            'report_name': report_name,
            'target_workspace': target_workspace_name,
            'target_semantic_model': target_model_name,
            'auto_deploy': auto_deploy,
            'auto_rebind': auto_rebind,
            'message': f'Configuración {action} para {report_name} → {target_workspace_name} (rebind: {target_model_name})'
        }
    
    async def get_deployment_config(self, arguments: Dict[str, Any]) -> Dict:
        """Get deployment configuration for an artifact"""
        artifact_name = arguments['artifact_name']
        artifact_type = arguments['artifact_type']
        
        if artifact_type == 'SemanticModel':
            config = self.deploy_config.get_deployment_config_for_model(artifact_name)
        elif artifact_type == 'Report':
            config = self.deploy_config.get_deployment_config_for_report(artifact_name)
        else:
            raise ValueError(f"Tipo de artefacto no válido: {artifact_type}")
        
        if config:
            return {
                'success': True,
                'configured': True,
                'config': config,
                'message': f'Configuración encontrada para {artifact_name}'
            }
        else:
            return {
                'success': True,
                'configured': False,
                'config': None,
                'message': f'No hay configuración para {artifact_name}. Usa configure_{artifact_type.lower()}_deployment para crear una.'
            }
    
    async def list_deployment_configs(self, arguments: Dict[str, Any]) -> Dict:
        """List all deployment configurations"""
        artifact_type = arguments.get('artifact_type')
        
        if artifact_type == 'SemanticModel':
            semantic_models = self.deploy_config.db.list_semantic_model_configs()
            reports = []
        elif artifact_type == 'Report':
            semantic_models = []
            reports = self.deploy_config.db.list_report_configs()
        else:
            semantic_models = self.deploy_config.db.list_semantic_model_configs()
            reports = self.deploy_config.db.list_report_configs()

        profiles = self.deploy_config.db.list_deployment_profiles()
        
        logger.info(f"Listed configs: {len(profiles)} profiles, {len(semantic_models)} models, {len(reports)} reports")
        
        return {
            'success': True,
            'profiles': profiles,
            'semantic_models': semantic_models,
            'reports': reports,
            'summary': {
                'profiles': len(profiles),
                'semantic_models': len(semantic_models),
                'reports': len(reports)
            }
        }
    
    async def setup_development_environment(self, arguments: Dict[str, Any]) -> Dict:
        """Setup a complete development environment configuration"""
        client = await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        workspace_id = arguments.get('workspace_id')
        semantic_models = arguments.get('semantic_models', [])
        report_mappings = arguments.get('report_mappings', {})
        
        # Resolve workspace if ID not provided
        if not workspace_id:
            workspace = client.get_workspace_by_name(workspace_name)
            if workspace:
                workspace_id = workspace['id']
            else:
                logger.warning(f"Workspace {workspace_name} not found")
        
        # Use deployment config manager to setup
        result = self.deploy_config.setup_development_environment(
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            semantic_models=semantic_models,
            reports=report_mappings
        )
        
        logger.info(f"Setup development environment: {workspace_name}")
        
        return {
            'success': True,
            'environment': 'development',
            'workspace': workspace_name,
            'configuration': result,
            'message': f'Ambiente de desarrollo configurado: {workspace_name}\n'
                      f'  - {len(result["semantic_models"])} modelos semánticos\n'
                      f'  - {len(result["reports"])} informes'
        }
