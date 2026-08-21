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
from powerbi_mcp_server.metadata.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class ToolHandlers:
    """MCP Tool handlers for Power BI operations"""
    
    def __init__(self, metadata_manager: MetadataManager):
        self.metadata = metadata_manager
        self.deploy_config = DeploymentConfigManager(metadata_manager.database)
        self._client: Optional[PowerBIClient] = None
        self._semantic_models: Optional[SemanticModelOperations] = None
        self._reports: Optional[ReportOperations] = None
        self._project_manager: Optional[ProjectManager] = None
    
    async def authenticate(self, arguments: Dict[str, Any]) -> Dict:
        """
        Start authentication. `method` picks how: 'auto' (default) tries
        cache -> az-cli -> Device Flow in order; 'device_flow' forces a
        fresh interactive login regardless of any cached/az-cli session;
        'az_cli' forces reuse of the current az login session only.
        """
        method = arguments.get("method", "auto")
        auth = get_authenticator()

        if method == "auto":
            message = await auth.start_device_flow()
        elif method == "device_flow":
            message = await auth.start_device_flow(force=True)
        elif method == "az_cli":
            message = await auth.authenticate_with_az_cli()
        else:
            return {
                "success": False,
                "error": f"Método de autenticación desconocido: '{method}'. Usa 'auto', 'device_flow' o 'az_cli'."
            }

        return {"success": True, "message": message}

    async def logout(self, arguments: Dict[str, Any]) -> Dict:
        """Clear the locally cached token so the next call requires re-authentication."""
        auth = get_authenticator()
        auth.logout()
        return {
            "success": True,
            "message": "Sesión cerrada. La próxima operación pedirá autenticarte de nuevo."
        }

    async def _ensure_authenticated(self) -> PowerBIClient:
        """Return authenticated client or raise AuthenticationRequired."""
        auth = get_authenticator()
        await auth.ensure_authenticated()  # raises AuthenticationRequired if no token

        if self._client is None:
            # Pass a token *provider* (not a snapshot) so the client keeps
            # working after the token is refreshed on disk.
            self._client = PowerBIClient(auth.get_token)
            self._semantic_models = SemanticModelOperations(self._client, self.metadata)
            self._reports = ReportOperations(self._client, self.metadata)
            self._project_manager = ProjectManager(
                self.metadata.database, self.deploy_config, self.metadata,
                self._client, self._semantic_models, self._reports
            )

        return self._client

    async def _resolve_rebind_model(
        self,
        model_workspace_id: str,
        model_workspace_name: str,
        model_name: str,
        source_dir: Optional[Path] = None,
        user_email: Optional[str] = None,
    ):
        """
        Resolve a rebind target semantic model by name, safely.

        Resolution order:
          1. Exactly one exact name match -> use it.
          2. No exact match but a sibling '{model_name}.SemanticModel' folder
             exists next to source_dir -> deploy that model first and use its
             new ID (PBIP project with report + model, model not published yet).
          3. Ambiguous (multiple exact or only partial matches) -> return a
             needs_disambiguation response instead of guessing.
          4. Nothing found -> raise.

        Returns:
            (semantic_model_id, display_name, None) on success, or
            (None, None, response_dict) when the caller must return that
            response to the client instead of proceeding.
        """
        models = self._client.list_workspace_items(model_workspace_id, 'SemanticModel')
        exact = [m for m in models if m['displayName'] == model_name]
        if len(exact) == 1:
            return exact[0]['id'], exact[0]['displayName'], None

        # Model not published yet: deploy the local sibling model first
        if not exact and source_dir is not None:
            sibling = source_dir.parent / f"{model_name}.SemanticModel"
            if sibling.is_dir():
                logger.info(
                    f"Rebind target '{model_name}' not found in workspace; "
                    f"deploying sibling model from {sibling} first"
                )
                deploy_result = await self._semantic_models.upload_pbip(
                    workspace_id=model_workspace_id,
                    workspace_name=model_workspace_name,
                    directory_path=sibling,
                    dataset_name=model_name,
                    user_email=user_email,
                )
                return deploy_result['dataset_id'], model_name, None

        partial = [m for m in models if model_name.lower() in m['displayName'].lower()]
        candidates = exact if len(exact) > 1 else partial
        if candidates:
            return None, None, {
                'success': False,
                'needs_disambiguation': True,
                'message': f"Hay varios modelos que coinciden con '{model_name}' en "
                           f"'{model_workspace_name}'. Indica el nombre exacto y reintenta.",
                'candidates': [
                    {'id': m['id'], 'displayName': m['displayName']} for m in candidates
                ],
            }

        raise ValueError(
            f"Modelo semántico no encontrado para reenlace: {model_name} "
            f"(workspace: {model_workspace_name})"
        )

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

        # PBIX download is not supported: the Power BI REST API has no
        # dataset-level export endpoint. Models download as PBIP.
        if format == 'pbix':
            return {
                'success': False,
                'error': "La descarga de modelos en PBIX no está soportada por la API de Power BI "
                         "(el export PBIX es solo de informes). Usa el formato 'pbip'."
            }

        # Download
        auth = get_authenticator()
        user_info = auth.get_user_info() or {}

        result = await self._semantic_models.download_pbip(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            target_dir=target_path,
            user_email=user_info.get('user_email')
        )

        return result
    
    async def upload_semantic_model(self, arguments: Dict[str, Any]) -> Dict:
        """Upload a semantic model"""
        await self._ensure_authenticated()
        
        workspace_name = arguments['workspace_name']
        source_path = Path(arguments['source_path'])
        dataset_name = arguments.get('dataset_name')
        folder_path = arguments.get('folder_path')

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
        user_info = auth.get_user_info() or {}

        if format == 'pbix':
            result = await self._semantic_models.upload_pbix(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                file_path=source_path,
                dataset_name=dataset_name,
                user_email=user_info.get('user_email'),
                folder_path=folder_path
            )
        else:  # pbip
            result = await self._semantic_models.upload_pbip(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                directory_path=source_path,
                dataset_name=dataset_name,
                user_email=user_info.get('user_email'),
                folder_path=folder_path
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
        user_info = auth.get_user_info() or {}
        
        result = await self._reports.download_pbir(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            report_id=report_id,
            report_name=report_name,
            target_dir=target_path,
            user_email=user_info.get('user_email')
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
        folder_path = arguments.get('folder_path')

        # Find workspace
        workspace = self._client.get_workspace_by_name(workspace_name)
        if not workspace:
            raise ValueError(f"Workspace no encontrado: {workspace_name}")

        workspace_id = workspace['id']

        auth = get_authenticator()
        user_info = auth.get_user_info() or {}

        # Find semantic model if rebinding (optionally in a different workspace).
        # If the model isn't published yet but its .SemanticModel folder sits
        # next to the report folder (PBIP project), it gets deployed first.
        semantic_model_id = None
        model_workspace_id = None
        if rebind_to_model:
            model_workspace_id = workspace_id
            model_workspace_name = workspace_name
            if rebind_workspace_name:
                model_workspace = self._client.get_workspace_by_name(rebind_workspace_name)
                if not model_workspace:
                    raise ValueError(f"Workspace no encontrado: {rebind_workspace_name}")
                model_workspace_id = model_workspace['id']
                model_workspace_name = rebind_workspace_name

            semantic_model_id, _, pending = await self._resolve_rebind_model(
                model_workspace_id=model_workspace_id,
                model_workspace_name=model_workspace_name,
                model_name=rebind_to_model,
                source_dir=source_path,
                user_email=user_info.get('user_email'),
            )
            if pending:
                return pending

        # Upload
        result = await self._reports.upload_pbir(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            directory_path=source_path,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
            semantic_model_workspace_id=model_workspace_id,
            user_email=user_info.get('user_email'),
            folder_path=folder_path
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

        semantic_model_id, semantic_model_name, pending = await self._resolve_rebind_model(
            model_workspace_id=model_workspace_id,
            model_workspace_name=target_model_workspace_name,
            model_name=target_model_name,
        )
        if pending:
            return pending

        auth = get_authenticator()
        user_info = auth.get_user_info() or {}

        result = await self._reports.rebind_report(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
            semantic_model_name=semantic_model_name,
            semantic_model_workspace_name=target_model_workspace_name,
            user_email=user_info.get('user_email')
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
        user_info = auth.get_user_info() or {}
        user_email = user_info.get('user_email')

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
        profile_name = arguments.get('profile_name')
        profile_id = self.deploy_config.resolve_profile_id(profile_name)

        # Resolve workspace if ID not provided
        if not target_workspace_id:
            workspace = client.get_workspace_by_name(target_workspace_name)
            if workspace:
                target_workspace_id = workspace['id']
            else:
                logger.warning(f"Workspace {target_workspace_name} not found, saving name only")
                target_workspace_id = ''

        # Check if config already exists (scoped to the environment, if given)
        existing_config = self.deploy_config.db.get_semantic_model_config(model_name, profile_id=profile_id)

        if existing_config:
            # Update existing
            self.deploy_config.db.update_semantic_model_config(
                model_name=model_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                auto_deploy=auto_deploy,
                notes=notes,
                profile_id=profile_id
            )
            logger.info(f"Updated semantic model config: {model_name}")
            action = 'updated'
        else:
            # Create new
            config_id = self.deploy_config.db.create_semantic_model_config(
                model_name=model_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                profile_id=profile_id,
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
        profile_name = arguments.get('profile_name')
        profile_id = self.deploy_config.resolve_profile_id(profile_name)

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
        
        # Check if config already exists (scoped to the environment, if given)
        existing_config = self.deploy_config.db.get_report_config(report_name, profile_id=profile_id)

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
                notes=notes,
                profile_id=profile_id
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
                profile_id=profile_id,
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
        profile_name = arguments.get('profile_name')

        if artifact_type == 'SemanticModel':
            config = self.deploy_config.get_deployment_config_for_model(artifact_name, profile_name=profile_name)
        elif artifact_type == 'Report':
            config = self.deploy_config.get_deployment_config_for_report(artifact_name, profile_name=profile_name)
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

    # ========== Environment hierarchy ==========

    async def configure_environment(self, arguments: Dict[str, Any]) -> Dict:
        """Create or update a deployment environment (alias + stage_order)"""
        client = await self._ensure_authenticated()

        profile_name = arguments['profile_name']
        target_workspace_name = arguments['target_workspace_name']
        target_workspace_id = arguments.get('target_workspace_id')
        stage_order = arguments.get('stage_order')
        environment_type = arguments.get('environment_type', 'development')
        description = arguments.get('description')

        if not target_workspace_id:
            workspace = client.get_workspace_by_name(target_workspace_name)
            if workspace:
                target_workspace_id = workspace['id']
            else:
                logger.warning(f"Workspace {target_workspace_name} not found, saving name only")
                target_workspace_id = ''

        result = self.deploy_config.configure_environment(
            profile_name=profile_name,
            target_workspace_name=target_workspace_name,
            target_workspace_id=target_workspace_id,
            stage_order=stage_order,
            environment_type=environment_type,
            description=description
        )
        return {'success': True, **result}

    async def list_environments(self, arguments: Dict[str, Any]) -> Dict:
        """List deployment environments ordered by stage_order"""
        environments = self.deploy_config.list_environments()
        return {'success': True, 'environments': environments}

    # ========== Projects ==========

    async def create_project(self, arguments: Dict[str, Any]) -> Dict:
        await self._ensure_authenticated()
        result = self._project_manager.create_project(
            project_name=arguments['project_name'],
            description=arguments.get('description')
        )
        return {'success': True, **result}

    async def get_project(self, arguments: Dict[str, Any]) -> Dict:
        await self._ensure_authenticated()
        project = self._project_manager.get_project(arguments['project_name'])
        return {'success': True, 'project': project}

    async def list_projects(self, arguments: Dict[str, Any]) -> Dict:
        await self._ensure_authenticated()
        projects = self._project_manager.list_projects()
        return {'success': True, 'projects': projects}

    async def add_project_artifact(self, arguments: Dict[str, Any]) -> Dict:
        await self._ensure_authenticated()
        result = self._project_manager.add_project_artifact(
            project_name=arguments['project_name'],
            artifact_type=arguments['artifact_type'],
            artifact_name=arguments['artifact_name'],
            rebind_to_artifact_name=arguments.get('rebind_to_artifact_name'),
            sequence_order=arguments.get('sequence_order'),
            notes=arguments.get('notes'),
            folder_path=arguments.get('folder_path')
        )
        return {'success': True, **result}

    async def remove_project_artifact(self, arguments: Dict[str, Any]) -> Dict:
        await self._ensure_authenticated()
        removed = self._project_manager.remove_project_artifact(
            project_name=arguments['project_name'],
            artifact_type=arguments['artifact_type'],
            artifact_name=arguments['artifact_name']
        )
        return {'success': True, 'removed': removed}

    async def deploy_project(self, arguments: Dict[str, Any]) -> Dict:
        """Explicit path: push a project from a local folder into any environment
        (hotfix/emergency path — bypasses the promotion chain, no drift check)."""
        await self._ensure_authenticated()
        user_info = get_authenticator().get_user_info() or {}
        result = await self._project_manager.deploy_project(
            project_name=arguments['project_name'],
            environment=arguments['environment'],
            source_dir=Path(arguments['source_dir']),
            user_email=user_info.get('user_email'),
            respect_local_structure=arguments.get('respect_local_structure', False)
        )
        return result

    async def promote_project(self, arguments: Dict[str, Any]) -> Dict:
        """Default path: move a project from the predecessor environment (by
        stage_order) into the target environment, in-memory, with drift check."""
        await self._ensure_authenticated()
        user_info = get_authenticator().get_user_info() or {}
        result = await self._project_manager.promote_project(
            project_name=arguments['project_name'],
            environment=arguments['environment'],
            confirm_drift=arguments.get('confirm_drift', False),
            user_email=user_info.get('user_email')
        )
        return result

    async def get_project_deployment_structure(self, arguments: Dict[str, Any]) -> Dict:
        """Read-only: artifacts, configured target folders, and known deployment
        state per environment for a project."""
        await self._ensure_authenticated()
        structure = self._project_manager.get_deployment_structure(arguments['project_name'])
        return {'success': True, 'structure': structure}

    async def list_fabric_capacities(self, arguments: Dict[str, Any]) -> Dict:
        client = await self._ensure_authenticated()
        capacities = client.list_capacities()
        return {'success': True, 'capacities': capacities}

    async def configure_project_workspace(self, arguments: Dict[str, Any]) -> Dict:
        """Manual mode: register (creating if missing) the workspace a project
        uses for one environment, optionally scoped to one artifact type."""
        await self._ensure_authenticated()
        result = await self._project_manager.configure_project_workspace(
            project_name=arguments['project_name'],
            environment=arguments['environment'],
            workspace_name=arguments['workspace_name'],
            artifact_type=arguments.get('artifact_type'),
            capacity_id=arguments.get('capacity_id')
        )
        return {'success': True, **result}

    async def auto_provision_project_workspaces(self, arguments: Dict[str, Any]) -> Dict:
        """Automatic mode: ensures dev/acc/prod environments exist and creates/
        registers one workspace per environment per artifact type, following
        the '{project}_{semantic|reports}{_dev|_acc|}' naming convention."""
        await self._ensure_authenticated()
        result = await self._project_manager.auto_provision_project_workspaces(
            project_name=arguments['project_name'],
            capacity_id=arguments.get('capacity_id')
        )
        return result

    async def get_deployment_tree(self, arguments: Dict[str, Any]) -> Dict:
        """Read-only ASCII tree of project(s) -> environments -> simulated
        folders -> artifacts, with resolved workspace and last deploy date."""
        await self._ensure_authenticated()
        tree = self._project_manager.render_deployment_tree(arguments.get('project_name'))
        return {'success': True, 'tree': tree}
