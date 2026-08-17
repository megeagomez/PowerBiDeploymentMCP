"""
Deployment Configuration Helper

Manages deployment configurations and provides helper methods for
automated deployments with semantic model and report rebinding.
"""

import logging
from typing import Dict, List, Optional, Tuple

from powerbi_mcp_server.metadata.database import MetadataDatabase

logger = logging.getLogger(__name__)


class DeploymentConfigManager:
    """
    Manages deployment configurations for automated deployments
    """
    
    def __init__(self, database: MetadataDatabase):
        self.db = database
    
    def setup_development_environment(
        self,
        workspace_name: str,
        workspace_id: Optional[str] = None,
        semantic_models: Optional[List[str]] = None,
        reports: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        Setup development environment configuration
        
        Args:
            workspace_name: Name of the development workspace
            workspace_id: Optional workspace ID
            semantic_models: List of semantic model names to deploy to this workspace
            reports: Dict of {report_name: semantic_model_name} for rebinding
        
        Returns:
            Configuration summary
        """
        # Create or get development profile
        profile = self.db.get_deployment_profile('development')
        if not profile:
            profile_id = self.db.create_deployment_profile(
                profile_name='development',
                target_workspace_name=workspace_name,
                target_workspace_id=workspace_id,
                environment_type='development',
                description='Development environment for Power BI assets'
            )
        else:
            profile_id = profile['id']
        
        # Configure semantic models
        model_configs = []
        if semantic_models:
            for model_name in semantic_models:
                config_id = self.db.create_semantic_model_config(
                    model_name=model_name,
                    target_workspace_id=workspace_id or '',
                    target_workspace_name=workspace_name,
                    profile_id=profile_id,
                    auto_deploy=True,
                    notes='Auto-configured for development'
                )
                model_configs.append({
                    'id': config_id,
                    'model_name': model_name,
                    'target_workspace': workspace_name
                })
                logger.info(f"Configured semantic model: {model_name} -> {workspace_name}")
        
        # Configure reports with rebinding
        report_configs = []
        if reports:
            for report_name, semantic_model_name in reports.items():
                config_id = self.db.create_report_config(
                    report_name=report_name,
                    target_workspace_id=workspace_id or '',
                    target_workspace_name=workspace_name,
                    target_semantic_model_name=semantic_model_name,
                    target_model_workspace_name=workspace_name,
                    profile_id=profile_id,
                    auto_deploy=True,
                    auto_rebind=True,
                    notes=f'Auto-configured for development, rebind to {semantic_model_name}'
                )
                report_configs.append({
                    'id': config_id,
                    'report_name': report_name,
                    'target_workspace': workspace_name,
                    'rebind_to': semantic_model_name
                })
                logger.info(f"Configured report: {report_name} -> {workspace_name} (rebind to {semantic_model_name})")
        
        return {
            'profile_id': profile_id,
            'workspace_name': workspace_name,
            'semantic_models': model_configs,
            'reports': report_configs
        }
    
    def get_deployment_config_for_model(self, model_name: str, profile_name: Optional[str] = None) -> Optional[Dict]:
        """
        Get deployment configuration for a semantic model, optionally scoped to
        one environment (profile_name). Without profile_name, returns the most
        recently created config regardless of environment (legacy behaviour).

        Returns:
            Configuration dict or None if not configured
        """
        profile_id = self.resolve_profile_id(profile_name)
        config = self.db.get_semantic_model_config(model_name, profile_id=profile_id)
        if config:
            logger.info(f"Found config for model: {model_name} -> {config['target_workspace_name']}")
        else:
            logger.info(f"No config found for model: {model_name}")
        return config

    def get_deployment_config_for_report(self, report_name: str, profile_name: Optional[str] = None) -> Optional[Dict]:
        """
        Get deployment configuration for a report, optionally scoped to one
        environment (profile_name). Without profile_name, returns the most
        recently created config regardless of environment (legacy behaviour).

        Returns:
            Configuration dict or None if not configured
        """
        profile_id = self.resolve_profile_id(profile_name)
        config = self.db.get_report_config(report_name, profile_id=profile_id)
        if config:
            logger.info(f"Found config for report: {report_name} -> {config['target_workspace_name']}")
            if config['target_semantic_model_name']:
                logger.info(f"  Rebind to: {config['target_semantic_model_name']}")
        else:
            logger.info(f"No config found for report: {report_name}")
        return config

    def resolve_profile_id(self, profile_name: Optional[str]) -> Optional[int]:
        if not profile_name:
            return None
        profile = self.db.get_deployment_profile(profile_name)
        if not profile:
            raise ValueError(f"Entorno desconocido: '{profile_name}'")
        return profile['id']

    # ========== Environment hierarchy (stage_order) ==========

    def configure_environment(
        self,
        profile_name: str,
        target_workspace_name: Optional[str] = None,
        target_workspace_id: Optional[str] = None,
        stage_order: Optional[int] = None,
        environment_type: str = 'development',
        description: Optional[str] = None
    ) -> Dict:
        """
        Create or update a deployment environment (alias + optional position
        in the promotion chain). target_workspace_name can be omitted for an
        environment that only ever gets used through per-project workspace
        overrides (see ProjectManager.configure_project_workspace) — it just
        won't have a default workspace of its own. Raises ValueError if
        stage_order is already owned by a different environment.
        """
        if stage_order is not None:
            for other in self.db.list_deployment_profiles():
                if other['profile_name'] != profile_name and other.get('stage_order') == stage_order:
                    raise ValueError(
                        f"stage_order {stage_order} ya está asignado al entorno '{other['profile_name']}'"
                    )

        existing = self.db.get_deployment_profile(profile_name)
        if existing:
            self.db.update_deployment_profile(
                profile_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                stage_order=stage_order,
                environment_type=environment_type,
                description=description
            )
            profile_id = existing['id']
            action = 'updated'
        else:
            profile_id = self.db.create_deployment_profile(
                profile_name=profile_name,
                target_workspace_id=target_workspace_id,
                target_workspace_name=target_workspace_name,
                environment_type=environment_type,
                description=description,
                stage_order=stage_order
            )
            action = 'created'

        return {
            'id': profile_id,
            'profile_name': profile_name,
            'target_workspace_name': target_workspace_name,
            'stage_order': stage_order,
            'action': action
        }

    def list_environments(self) -> List[Dict]:
        """List all environments ordered by stage_order (unordered ones last)."""
        profiles = self.db.list_deployment_profiles()
        return sorted(
            profiles,
            key=lambda p: (p.get('stage_order') is None, p.get('stage_order') or 0, p['profile_name'])
        )

    def get_predecessor_profile(self, profile_name: str) -> Optional[Dict]:
        """
        Resolve the environment immediately BEFORE the given one in the
        promotion chain (the environment whose stage_order is the highest
        value still below the target's stage_order).
        """
        target = self.db.get_deployment_profile(profile_name)
        if not target or target.get('stage_order') is None:
            return None
        candidates = [
            p for p in self.db.list_deployment_profiles()
            if p.get('stage_order') is not None and p['stage_order'] < target['stage_order']
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p['stage_order'])
    
    def should_auto_deploy(self, artifact_name: str, artifact_type: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if an artifact should be auto-deployed
        
        Args:
            artifact_name: Name of the artifact
            artifact_type: 'SemanticModel' or 'Report'
        
        Returns:
            Tuple of (should_deploy, config)
        """
        if artifact_type == 'SemanticModel':
            config = self.get_deployment_config_for_model(artifact_name)
        elif artifact_type == 'Report':
            config = self.get_deployment_config_for_report(artifact_name)
        else:
            return False, None
        
        if config and config.get('auto_deploy'):
            return True, config
        
        return False, config
    
    def get_rebind_info(self, report_name: str) -> Optional[Dict]:
        """
        Get semantic model rebinding information for a report
        
        Returns:
            Dict with rebinding info or None
        """
        config = self.db.get_report_config(report_name)
        
        if not config:
            return None
        
        if config['auto_rebind'] and config['target_semantic_model_name']:
            return {
                'rebind': True,
                'semantic_model_name': config['target_semantic_model_name'],
                'model_workspace_name': config.get('target_model_workspace_name'),
                'model_workspace_id': config.get('target_model_workspace_id')
            }
        
        return None
    
    def list_all_configs(self) -> Dict:
        """
        List all deployment configurations
        
        Returns:
            Dict with profiles, models, and reports
        """
        profiles = self.db.list_deployment_profiles()
        semantic_models = self.db.list_semantic_model_configs()
        reports = self.db.list_report_configs()
        
        return {
            'profiles': profiles,
            'semantic_models': semantic_models,
            'reports': reports
        }
    
    def prompt_and_configure_model(self, model_name: str) -> Dict:
        """
        Interactive configuration for a semantic model
        This would typically prompt the user, but returns structure for MCP prompt
        
        Returns:
            Configuration structure for MCP prompt
        """
        return {
            'artifact_type': 'SemanticModel',
            'artifact_name': model_name,
            'questions': [
                {
                    'id': 'target_workspace',
                    'question': f'¿A qué workspace debe ir el modelo "{model_name}"?',
                    'type': 'workspace_selector'
                },
                {
                    'id': 'auto_deploy',
                    'question': '¿Desplegar automáticamente en futuras subidas?',
                    'type': 'boolean',
                    'default': True
                }
            ]
        }
    
    def prompt_and_configure_report(self, report_name: str) -> Dict:
        """
        Interactive configuration for a report
        This would typically prompt the user, but returns structure for MCP prompt
        
        Returns:
            Configuration structure for MCP prompt
        """
        return {
            'artifact_type': 'Report',
            'artifact_name': report_name,
            'questions': [
                {
                    'id': 'target_workspace',
                    'question': f'¿A qué workspace debe ir el informe "{report_name}"?',
                    'type': 'workspace_selector'
                },
                {
                    'id': 'needs_rebind',
                    'question': '¿Necesita reenlazarse a un modelo semántico?',
                    'type': 'boolean',
                    'default': True
                },
                {
                    'id': 'target_model',
                    'question': '¿A qué modelo semántico debe apuntar?',
                    'type': 'semantic_model_selector',
                    'conditional': 'needs_rebind'
                },
                {
                    'id': 'auto_deploy',
                    'question': '¿Desplegar automáticamente en futuras subidas?',
                    'type': 'boolean',
                    'default': True
                }
            ]
        }
