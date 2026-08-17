"""
Project Manager

Orchestrates multi-artifact "projects" (a named group of semantic models +
reports) across the environment hierarchy defined in deployment_profiles.
Two verbs are exposed:

- deploy_project:  explicit, from a local PBIP/PBIR folder into ANY named
                    environment. No drift check — this IS the bypass path,
                    meant for emergencies/hotfixes.
- promote_project: the default verb. Moves whatever is currently deployed in
                    the predecessor environment (resolved via stage_order)
                    into the target environment, entirely in-memory
                    (client.get_item_definition -> client.upsert_item), with
                    a read-only drift scan first that can block the write
                    phase pending explicit confirmation.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from powerbi_mcp_server.api import PowerBIClient
from powerbi_mcp_server.api.semantic_models import SemanticModelOperations
from powerbi_mcp_server.api.reports import ReportOperations
from powerbi_mcp_server.metadata import MetadataManager
from powerbi_mcp_server.metadata.deployment_config import DeploymentConfigManager
from powerbi_mcp_server.metadata.drift import check_drift, hash_definition
from powerbi_mcp_server.metadata.repository import MetadataRepository

logger = logging.getLogger(__name__)

_ARTIFACT_TYPE_ALIASES = {
    'model': 'SemanticModel',
    'semanticmodel': 'SemanticModel',
    'semantic_model': 'SemanticModel',
    'report': 'Report',
}


class ProjectManager:
    """Groups semantic models + reports into projects and moves them between environments."""

    def __init__(
        self,
        repository: MetadataRepository,
        deploy_config: DeploymentConfigManager,
        metadata_manager: MetadataManager,
        client: PowerBIClient,
        semantic_model_ops: SemanticModelOperations,
        report_ops: ReportOperations
    ):
        self.repo = repository
        self.deploy_config = deploy_config
        self.metadata = metadata_manager
        self.client = client
        self.semantic_models = semantic_model_ops
        self.reports = report_ops

    # ========== Project / artifact CRUD ==========

    @staticmethod
    def normalize_artifact_type(artifact_type: str) -> str:
        normalized = _ARTIFACT_TYPE_ALIASES.get(artifact_type.strip().lower())
        if not normalized:
            raise ValueError(f"Tipo de artefacto desconocido: '{artifact_type}' (usa 'model' o 'report')")
        return normalized

    def _require_project(self, project_name: str) -> Dict:
        project = self.repo.get_project_by_name(project_name)
        if not project:
            raise ValueError(f"Proyecto no encontrado: '{project_name}'")
        return project

    def _ordered_artifacts(self, project_id: int) -> List[Dict]:
        artifacts = self.repo.list_project_artifacts(project_id)
        return sorted(
            artifacts,
            key=lambda a: (
                a['artifact_type'] != 'SemanticModel',
                a.get('sequence_order') if a.get('sequence_order') is not None else 0,
                a['artifact_name']
            )
        )

    def create_project(self, project_name: str, description: Optional[str] = None) -> Dict:
        if self.repo.get_project_by_name(project_name):
            raise ValueError(f"El proyecto '{project_name}' ya existe")
        project_id = self.repo.create_project(project_name, description)
        return {'id': project_id, 'project_name': project_name, 'description': description}

    def get_project(self, project_name: str) -> Dict:
        project = self._require_project(project_name)
        return {**project, 'artifacts': self._ordered_artifacts(project['id'])}

    def list_projects(self) -> List[Dict]:
        return self.repo.list_projects()

    def add_project_artifact(
        self,
        project_name: str,
        artifact_type: str,
        artifact_name: str,
        rebind_to_artifact_name: Optional[str] = None,
        sequence_order: Optional[int] = None,
        notes: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> Dict:
        project = self._require_project(project_name)
        artifact_type = self.normalize_artifact_type(artifact_type)

        if rebind_to_artifact_name:
            if artifact_type != 'Report':
                raise ValueError("rebind_to_artifact_name solo aplica a artefactos de tipo 'report'")
            existing = self.repo.list_project_artifacts(project['id'])
            model_in_project = any(
                a['artifact_type'] == 'SemanticModel' and a['artifact_name'] == rebind_to_artifact_name
                for a in existing
            )
            if not model_in_project:
                raise ValueError(
                    f"'{rebind_to_artifact_name}' debe ser un modelo semántico ya añadido al proyecto "
                    f"'{project_name}' antes de poder usarlo como destino de rebind"
                )

        artifact_id = self.repo.add_project_artifact(
            project['id'], artifact_type, artifact_name, rebind_to_artifact_name, sequence_order, notes,
            folder_path=folder_path
        )
        return {
            'id': artifact_id, 'project_name': project_name,
            'artifact_type': artifact_type, 'artifact_name': artifact_name,
            'rebind_to_artifact_name': rebind_to_artifact_name,
            'folder_path': folder_path
        }

    def remove_project_artifact(self, project_name: str, artifact_type: str, artifact_name: str) -> bool:
        project = self._require_project(project_name)
        artifact_type = self.normalize_artifact_type(artifact_type)
        return self.repo.remove_project_artifact(project['id'], artifact_type, artifact_name)

    # ========== Per-project workspace overrides ==========

    def _resolve_target_workspace(self, project_id: int, profile: Dict, artifact_type: str) -> Dict:
        """
        Resolve which workspace an artifact of a project should use for a given
        environment. A project-specific override (see configure_project_workspace)
        takes precedence over the environment's own default workspace:

        1. An override registered specifically for this artifact_type.
        2. A "combined" override (artifact_type=None) covering both types.
        3. The environment's own target_workspace_id/name (may be None).

        Returns {'workspace_id': ..., 'workspace_name': ...} — both may be None
        if nothing resolves, which callers must treat as "not configured".
        """
        overrides = self.repo.list_project_environment_workspaces(project_id, profile['id'])
        specific = next((o for o in overrides if o['artifact_type'] == artifact_type), None)
        if specific:
            return {'workspace_id': specific['workspace_id'], 'workspace_name': specific['workspace_name']}
        combined = next((o for o in overrides if o['artifact_type'] is None), None)
        if combined:
            return {'workspace_id': combined['workspace_id'], 'workspace_name': combined['workspace_name']}
        return {
            'workspace_id': profile.get('target_workspace_id'),
            'workspace_name': profile.get('target_workspace_name')
        }

    async def configure_project_workspace(
        self, project_name: str, environment: str, workspace_name: str,
        artifact_type: Optional[str] = None, capacity_id: Optional[str] = None
    ) -> Dict:
        """
        Manual mode: register the workspace a project should use for one
        environment (optionally scoped to 'model' or 'report' — omit to cover
        both). Creates the workspace in Fabric if it doesn't already exist.
        This is the same primitive auto_provision_project_workspaces calls in
        a loop for the automatic dev/acc/prod naming convention.
        """
        project = self._require_project(project_name)
        profile = self.deploy_config.db.get_deployment_profile(environment)
        if not profile:
            raise ValueError(f"Entorno desconocido: '{environment}'")

        normalized_type = self.normalize_artifact_type(artifact_type) if artifact_type else None

        workspace = self.client.get_workspace_by_name(workspace_name)
        created = False
        if not workspace:
            workspace = self.client.create_workspace(workspace_name, capacity_id=capacity_id)
            created = True

        self.repo.upsert_project_environment_workspace(
            project_id=project['id'], profile_id=profile['id'], artifact_type=normalized_type,
            workspace_id=workspace['id'], workspace_name=workspace_name
        )
        return {
            'project_name': project_name, 'environment': environment,
            'artifact_type': normalized_type or 'combined',
            'workspace_id': workspace['id'], 'workspace_name': workspace_name, 'created': created
        }

    # Fixed automatic environment chain: alias, stage_order, workspace-name suffix
    _AUTO_ENVIRONMENTS = [('dev', 1, '_dev'), ('acc', 2, '_acc'), ('prod', 3, '')]
    _AUTO_TYPE_LABELS = [('SemanticModel', 'semantic'), ('Report', 'reports')]

    async def auto_provision_project_workspaces(
        self, project_name: str, capacity_id: Optional[str] = None
    ) -> Dict:
        """
        Automatic mode: ensures the dev/acc/prod environments exist (creating
        any that are missing, with stage_order 1/2/3 and no default workspace
        of their own), then creates/registers one workspace per environment
        per artifact type, named '{project}_{semantic|reports}{_dev|_acc|}'
        (prod has no suffix) — e.g. for project "Ventas": Ventas_semantic_dev,
        Ventas_reports_dev, Ventas_semantic_acc, Ventas_reports_acc,
        Ventas_semantic, Ventas_reports.
        """
        self._require_project(project_name)

        environments_created = []
        for profile_name, stage_order, _ in self._AUTO_ENVIRONMENTS:
            if not self.deploy_config.db.get_deployment_profile(profile_name):
                self.deploy_config.configure_environment(profile_name, stage_order=stage_order)
                environments_created.append(profile_name)

        workspaces = []
        for profile_name, _, suffix in self._AUTO_ENVIRONMENTS:
            for artifact_type, type_label in self._AUTO_TYPE_LABELS:
                workspace_name = f"{project_name}_{type_label}{suffix}"
                result = await self.configure_project_workspace(
                    project_name, profile_name, workspace_name,
                    artifact_type=artifact_type, capacity_id=capacity_id
                )
                workspaces.append(result)

        return {
            'success': True, 'project_name': project_name,
            'environments_created': environments_created, 'workspaces': workspaces
        }

    # ========== Deploy (explicit, local folder -> any environment) ==========

    async def deploy_project(
        self, project_name: str, environment: str, source_dir: Path, user_email: Optional[str] = None,
        respect_local_structure: bool = False
    ) -> Dict:
        project = self._require_project(project_name)
        artifacts = self._ordered_artifacts(project['id'])
        if not artifacts:
            raise ValueError(f"El proyecto '{project_name}' no tiene artefactos configurados")

        target = self.deploy_config.db.get_deployment_profile(environment)
        if not target:
            raise ValueError(f"Entorno desconocido: '{environment}'")

        source_dir = Path(source_dir)
        model_ids_by_name: Dict[str, str] = {}
        model_workspaces_by_name: Dict[str, Dict] = {}
        summary = {'semantic_models': [], 'reports': [], 'errors': []}

        try:
            for artifact in artifacts:
                if artifact['artifact_type'] != 'SemanticModel':
                    continue
                ws = self._resolve_target_workspace(project['id'], target, 'SemanticModel')
                if not ws['workspace_id']:
                    raise ValueError(
                        f"No hay workspace configurado para modelos semánticos del proyecto '{project_name}' "
                        f"en el entorno '{environment}' (ni específico ni en el propio entorno)"
                    )
                model_dir, derived_folder = self._locate_artifact_dir(
                    source_dir, artifact['artifact_name'], '.SemanticModel', respect_local_structure
                )
                folder_path = artifact.get('folder_path') or derived_folder
                result = await self.semantic_models.upload_pbip(
                    workspace_id=ws['workspace_id'],
                    workspace_name=ws['workspace_name'],
                    directory_path=model_dir,
                    dataset_name=artifact['artifact_name'],
                    user_email=user_email,
                    folder_path=folder_path
                )
                model_ids_by_name[artifact['artifact_name']] = result['dataset_id']
                model_workspaces_by_name[artifact['artifact_name']] = ws
                self._record_state_after_write(
                    project['id'], target['id'], ws['workspace_id'], ws['workspace_name'],
                    'SemanticModel', artifact['artifact_name'],
                    result['dataset_id'], source_profile_id=None, operation='deploy', user_email=user_email
                )
                summary['semantic_models'].append(result)

            for artifact in artifacts:
                if artifact['artifact_type'] != 'Report':
                    continue
                ws = self._resolve_target_workspace(project['id'], target, 'Report')
                if not ws['workspace_id']:
                    raise ValueError(
                        f"No hay workspace configurado para informes del proyecto '{project_name}' "
                        f"en el entorno '{environment}' (ni específico ni en el propio entorno)"
                    )
                report_dir, derived_folder = self._locate_artifact_dir(
                    source_dir, artifact['artifact_name'], '.Report', respect_local_structure
                )
                folder_path = artifact.get('folder_path') or derived_folder
                rebind_model_id = None
                rebind_model_ws = None
                if artifact.get('rebind_to_artifact_name'):
                    rebind_model_id = model_ids_by_name.get(artifact['rebind_to_artifact_name'])
                    rebind_model_ws = model_workspaces_by_name.get(artifact['rebind_to_artifact_name'])
                result = await self.reports.upload_pbir(
                    workspace_id=ws['workspace_id'],
                    workspace_name=ws['workspace_name'],
                    directory_path=report_dir,
                    report_name=artifact['artifact_name'],
                    semantic_model_id=rebind_model_id,
                    semantic_model_workspace_id=rebind_model_ws['workspace_id'] if rebind_model_ws else None,
                    user_email=user_email,
                    folder_path=folder_path
                )
                self._record_state_after_write(
                    project['id'], target['id'], ws['workspace_id'], ws['workspace_name'],
                    'Report', artifact['artifact_name'],
                    result['report_id'], source_profile_id=None, operation='deploy', user_email=user_email
                )
                summary['reports'].append(result)

            self.repo.record_promotion_event(
                project_id=project['id'], operation='deploy', to_profile_id=target['id'],
                from_profile_id=None, artifact_summary=json.dumps(summary, default=str),
                drift_detected=False, drift_confirmed=False, status='success', initiated_by=user_email
            )
            return {'success': True, 'target_environment': target['profile_name'], **summary}
        except Exception as exc:
            self.repo.record_promotion_event(
                project_id=project['id'], operation='deploy', to_profile_id=target['id'],
                from_profile_id=None, artifact_summary=json.dumps(summary, default=str),
                drift_detected=False, drift_confirmed=False, status='failed',
                error_message=str(exc), initiated_by=user_email
            )
            raise

    def _locate_artifact_dir(
        self, source_dir: Path, artifact_name: str, suffix: str, respect_local_structure: bool
    ) -> "tuple[Path, Optional[str]]":
        """
        Resolve the local directory for an artifact.

        Default (respect_local_structure=False): flat layout, always
        source_dir/{artifact_name}{suffix} — unchanged from before.

        With respect_local_structure=True: searches recursively under
        source_dir for {artifact_name}{suffix}. If found under a subfolder,
        that subfolder's path (relative to source_dir) becomes the derived
        target folder_path, so the workspace ends up mirroring the local
        layout. Raises on more than one match (ambiguous, won't guess).
        """
        flat_dir = source_dir / f"{artifact_name}{suffix}"
        if not respect_local_structure:
            return flat_dir, None

        matches = [p for p in source_dir.rglob(f"{artifact_name}{suffix}") if p.is_dir()]
        if not matches:
            return flat_dir, None
        if len(matches) > 1:
            options = ", ".join(str(m) for m in matches)
            raise ValueError(
                f"Varias carpetas coinciden con '{artifact_name}{suffix}' bajo {source_dir}: {options}. "
                "Elimina las duplicadas o desactiva --respect-local-structure para este artefacto."
            )

        found_dir = matches[0]
        relative_parent = found_dir.parent.relative_to(source_dir)
        folder_path = None if str(relative_parent) == '.' else relative_parent.as_posix()
        return found_dir, folder_path

    def _record_state_after_write(
        self, project_id: int, profile_id: int, workspace_id: str, workspace_name: str,
        artifact_type: str, artifact_name: str,
        item_id: str, source_profile_id: Optional[int], operation: str, user_email: Optional[str]
    ) -> None:
        live_def = self.client.get_item_definition(workspace_id, item_id)
        definition_hash = hash_definition(live_def.get('definition') or {})
        self.repo.upsert_environment_artifact_state(
            project_id=project_id, profile_id=profile_id, artifact_type=artifact_type,
            artifact_name=artifact_name, workspace_item_id=item_id,
            workspace_id=workspace_id, workspace_name=workspace_name,
            definition_hash=definition_hash, source_profile_id=source_profile_id,
            last_operation=operation, updated_by=user_email
        )

    # ========== Promote (default, in-memory, environment -> environment) ==========

    async def promote_project(
        self, project_name: str, environment: str, confirm_drift: bool = False, user_email: Optional[str] = None
    ) -> Dict:
        project = self._require_project(project_name)
        artifacts = self._ordered_artifacts(project['id'])
        if not artifacts:
            raise ValueError(f"El proyecto '{project_name}' no tiene artefactos configurados")

        target = self.deploy_config.db.get_deployment_profile(environment)
        if not target:
            raise ValueError(f"Entorno desconocido: '{environment}'")
        if target.get('stage_order') is None:
            raise ValueError(f"El entorno '{environment}' no tiene stage_order configurado; no se puede promocionar")

        source = self.deploy_config.get_predecessor_profile(environment)
        if not source:
            raise ValueError(f"No hay un entorno anterior en la cadena para promocionar hacia '{environment}'")

        fetched, drift_findings = self._scan_for_drift(project, artifacts, source, target)

        if drift_findings and not confirm_drift:
            self.repo.record_promotion_event(
                project_id=project['id'], operation='promote', to_profile_id=target['id'],
                from_profile_id=source['id'], artifact_summary=json.dumps(drift_findings, default=str),
                drift_detected=True, drift_confirmed=False, status='blocked_on_drift', initiated_by=user_email
            )
            return {
                'success': False,
                'needs_confirmation': True,
                'source_environment': source['profile_name'],
                'target_environment': target['profile_name'],
                'drift': drift_findings,
                'message': (
                    "Se detectó divergencia respecto a lo que se promocionaría normalmente. "
                    "Revisa 'drift' y reintenta con confirm_drift=True (--yes en el CLI) si quieres sobrescribir."
                )
            }

        try:
            summary = self._write_promotion(project, artifacts, source, target, fetched, user_email)
        except Exception as exc:
            self.repo.record_promotion_event(
                project_id=project['id'], operation='promote', to_profile_id=target['id'],
                from_profile_id=source['id'], artifact_summary=None,
                drift_detected=bool(drift_findings), drift_confirmed=bool(drift_findings) and confirm_drift,
                status='failed', error_message=str(exc), initiated_by=user_email
            )
            raise

        self.repo.record_promotion_event(
            project_id=project['id'], operation='promote', to_profile_id=target['id'],
            from_profile_id=source['id'], artifact_summary=json.dumps(summary, default=str),
            drift_detected=bool(drift_findings), drift_confirmed=bool(drift_findings) and confirm_drift,
            status='success', initiated_by=user_email
        )
        return {
            'success': True,
            'source_environment': source['profile_name'],
            'target_environment': target['profile_name'],
            'drift_confirmed': bool(drift_findings) and confirm_drift,
            **summary
        }

    def _scan_for_drift(self, project: Dict, artifacts: List[Dict], source: Dict, target: Dict):
        """Read-only phase: fetch each artifact's live definition from the source
        workspace and compare the target's tracked state against it. No writes."""
        fetched: Dict[tuple, Dict] = {}
        drift_findings = []

        for artifact in artifacts:
            item_type = artifact['artifact_type']
            source_ws = self._resolve_target_workspace(project['id'], source, item_type)
            if not source_ws['workspace_id']:
                raise ValueError(
                    f"No hay workspace configurado para {item_type} del proyecto '{project['project_name']}' "
                    f"en el entorno origen '{source['profile_name']}'"
                )
            target_ws = self._resolve_target_workspace(project['id'], target, item_type)
            if not target_ws['workspace_id']:
                raise ValueError(
                    f"No hay workspace configurado para {item_type} del proyecto '{project['project_name']}' "
                    f"en el entorno destino '{target['profile_name']}'"
                )

            source_items = self.client.list_workspace_items(source_ws['workspace_id'], item_type)
            source_item = next((i for i in source_items if i['displayName'] == artifact['artifact_name']), None)
            if not source_item:
                raise ValueError(
                    f"'{artifact['artifact_name']}' ({item_type}) no existe en el entorno origen "
                    f"'{source['profile_name']}' (workspace '{source_ws['workspace_name']}')"
                )
            source_definition = self.client.get_item_definition(source_ws['workspace_id'], source_item['id'])
            source_definition = source_definition.get('definition') or {}
            source_hash = hash_definition(source_definition)

            state = self.repo.get_environment_artifact_state(
                project['id'], target['id'], item_type, artifact['artifact_name']
            )
            target_live_hash = self._live_hash_if_present(target_ws['workspace_id'], item_type, state)

            check = check_drift(state, expected_source_profile_id=source['id'], target_live_hash=target_live_hash)
            fetched[(item_type, artifact['artifact_name'])] = {
                'definition': source_definition,
                'source_hash': source_hash,
                'target_workspace_id': target_ws['workspace_id'],
                'target_workspace_name': target_ws['workspace_name']
            }
            if check.has_drift:
                drift_findings.append({
                    'artifact_type': item_type,
                    'artifact_name': artifact['artifact_name'],
                    'reasons': check.reasons
                })

        return fetched, drift_findings

    def _live_hash_if_present(self, workspace_id: str, item_type: str, state: Optional[Dict]) -> Optional[str]:
        if not state or not state.get('workspace_item_id'):
            return None
        target_items = self.client.list_workspace_items(workspace_id, item_type)
        target_item = next((i for i in target_items if i['id'] == state['workspace_item_id']), None)
        if not target_item:
            return None
        target_live_def = self.client.get_item_definition(workspace_id, target_item['id'])
        return hash_definition(target_live_def.get('definition') or {})

    def _write_promotion(
        self, project: Dict, artifacts: List[Dict], source: Dict, target: Dict,
        fetched: Dict[tuple, Dict], user_email: Optional[str]
    ) -> Dict:
        summary = {'semantic_models': [], 'reports': [], 'errors': []}
        model_item_ids: Dict[str, str] = {}

        for artifact in artifacts:
            if artifact['artifact_type'] != 'SemanticModel':
                continue
            key = ('SemanticModel', artifact['artifact_name'])
            ws_id = fetched[key]['target_workspace_id']
            ws_name = fetched[key]['target_workspace_name']
            folder_id = self.client.resolve_or_create_folder_path(ws_id, artifact.get('folder_path'))
            item, created = self.client.upsert_item(
                ws_id, 'SemanticModel', artifact['artifact_name'],
                fetched[key]['definition'], folder_id=folder_id
            )
            model_item_ids[artifact['artifact_name']] = item['id']
            self.repo.upsert_environment_artifact_state(
                project_id=project['id'], profile_id=target['id'], artifact_type='SemanticModel',
                artifact_name=artifact['artifact_name'], workspace_item_id=item['id'],
                workspace_id=ws_id, workspace_name=ws_name,
                definition_hash=fetched[key]['source_hash'], source_profile_id=source['id'],
                last_operation='promote', updated_by=user_email
            )
            summary['semantic_models'].append({
                'artifact_name': artifact['artifact_name'], 'item_id': item['id'],
                'workspace_name': ws_name, 'operation': 'created' if created else 'updated'
            })

        for artifact in artifacts:
            if artifact['artifact_type'] != 'Report':
                continue
            key = ('Report', artifact['artifact_name'])
            ws_id = fetched[key]['target_workspace_id']
            ws_name = fetched[key]['target_workspace_name']
            folder_id = self.client.resolve_or_create_folder_path(ws_id, artifact.get('folder_path'))
            item, created = self.client.upsert_item(
                ws_id, 'Report', artifact['artifact_name'],
                fetched[key]['definition'], folder_id=folder_id
            )
            self.repo.upsert_environment_artifact_state(
                project_id=project['id'], profile_id=target['id'], artifact_type='Report',
                artifact_name=artifact['artifact_name'], workspace_item_id=item['id'],
                workspace_id=ws_id, workspace_name=ws_name,
                definition_hash=fetched[key]['source_hash'], source_profile_id=source['id'],
                last_operation='promote', updated_by=user_email
            )
            rebound_model_id = None
            if artifact.get('rebind_to_artifact_name'):
                model_id = model_item_ids.get(artifact['rebind_to_artifact_name'])
                if model_id:
                    # rebind_report only needs the REPORT's workspace — the dataset can
                    # live in a different workspace (e.g. split semantic/reports workspaces)
                    self.client.rebind_report(ws_id, item['id'], model_id)
                    self.metadata.track_report_model_relationship(
                        report_id=item['id'], report_name=artifact['artifact_name'],
                        semantic_model_id=model_id, semantic_model_name=artifact['rebind_to_artifact_name'],
                        workspace_id=ws_id, workspace_name=ws_name
                    )
                    rebound_model_id = model_id
            summary['reports'].append({
                'artifact_name': artifact['artifact_name'], 'item_id': item['id'],
                'workspace_name': ws_name, 'operation': 'created' if created else 'updated',
                'rebound_to_model_id': rebound_model_id
            })

        return summary

    # ========== Deployment structure (read-only overview) ==========

    def get_deployment_structure(self, project_name: str) -> Dict:
        """
        Read-only overview of a project's deployment configuration: every
        artifact with its configured target folder, and — for each configured
        environment — the target workspace and any already-known deployment
        state. Pure config/state read (no Fabric API calls), so it's fast and
        doesn't require live authentication beyond opening the database.
        """
        project = self._require_project(project_name)
        artifacts = self._ordered_artifacts(project['id'])
        environments = self.deploy_config.list_environments()

        artifact_summaries = [
            {
                'artifact_type': a['artifact_type'],
                'artifact_name': a['artifact_name'],
                'rebind_to_artifact_name': a.get('rebind_to_artifact_name'),
                'folder_path': a.get('folder_path')
            }
            for a in artifacts
        ]

        env_summaries = []
        for env in environments:
            env_artifacts = []
            for artifact in artifacts:
                state = self.repo.get_environment_artifact_state(
                    project['id'], env['id'], artifact['artifact_type'], artifact['artifact_name']
                )
                current_state = None
                if state:
                    promoted_from = None
                    if state.get('source_profile_id'):
                        source_profile = self.deploy_config.db.get_deployment_profile_by_id(state['source_profile_id'])
                        promoted_from = source_profile['profile_name'] if source_profile else None
                    current_state = {
                        'last_operation': state.get('last_operation'),
                        'promoted_from': promoted_from,
                        'updated_at': state.get('updated_at')
                    }
                resolved_ws = self._resolve_target_workspace(project['id'], env, artifact['artifact_type'])
                env_artifacts.append({
                    'artifact_type': artifact['artifact_type'],
                    'artifact_name': artifact['artifact_name'],
                    'target_workspace_name': resolved_ws['workspace_name'],
                    'target_folder_path': artifact.get('folder_path'),
                    'current_state': current_state
                })
            env_summaries.append({
                'profile_name': env['profile_name'],
                'stage_order': env.get('stage_order'),
                'target_workspace_name': env.get('target_workspace_name'),
                'artifacts': env_artifacts
            })

        return {
            'project_name': project['project_name'],
            'description': project.get('description'),
            'artifacts': artifact_summaries,
            'environments': env_summaries
        }

    # ========== Deployment tree (ASCII visualization) ==========

    def render_deployment_tree(self, project_name: Optional[str] = None) -> str:
        """
        Render an ASCII tree (using only '-', '|' and spaces) of: project ->
        environment -> simulated folder structure (from each artifact's
        folder_path) -> artifact, annotated with its resolved workspace and
        last deployment date if known. If project_name is omitted, renders
        every configured project.
        """
        if project_name:
            project_names = [project_name]
        else:
            project_names = [p['project_name'] for p in self.repo.list_projects()]

        if not project_names:
            return "(no hay proyectos configurados)"

        blocks = []
        for name in project_names:
            structure = self.get_deployment_structure(name)
            lines = [structure['project_name']]
            environments = structure['environments']
            for i, env in enumerate(environments):
                is_last_env = i == len(environments) - 1
                label = f"{env['profile_name']}"
                if env.get('stage_order') is not None:
                    label += f" (stage_order={env['stage_order']})"
                lines.append(f"|-- {label}")
                child_prefix = "    " if is_last_env else "|   "
                folder_tree = self._build_folder_tree(env['artifacts'])
                lines.extend(self._render_folder_tree(folder_tree, child_prefix))
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    @staticmethod
    def _build_folder_tree(env_artifacts: List[Dict]) -> Dict:
        root = {'children': {}, 'artifacts': []}
        for artifact in env_artifacts:
            node = root
            folder_path = artifact.get('target_folder_path')
            segments = [s for s in folder_path.split('/') if s] if folder_path else []
            for segment in segments:
                node = node['children'].setdefault(segment, {'children': {}, 'artifacts': []})
            node['artifacts'].append(artifact)
        return root

    @classmethod
    def _render_folder_tree(cls, node: Dict, prefix: str) -> List[str]:
        lines: List[str] = []
        folder_entries = sorted(node['children'].items())
        artifact_entries = sorted(node['artifacts'], key=lambda a: a['artifact_name'])
        total = len(folder_entries) + len(artifact_entries)
        index = 0

        for folder_name, child in folder_entries:
            is_last = index == total - 1
            lines.append(f"{prefix}|-- {folder_name}")
            lines.extend(cls._render_folder_tree(child, prefix + ("    " if is_last else "|   ")))
            index += 1

        for artifact in artifact_entries:
            lines.append(f"{prefix}|-- {cls._format_tree_artifact(artifact)}")
            index += 1

        return lines

    @staticmethod
    def _format_tree_artifact(artifact: Dict) -> str:
        state = artifact.get('current_state')
        when = state['updated_at'] if state else 'sin desplegar'
        workspace = artifact.get('target_workspace_name') or '(sin workspace configurado)'
        return f"[{artifact['artifact_type']}] {artifact['artifact_name']}  ({workspace}, últ. despliegue: {when})"
