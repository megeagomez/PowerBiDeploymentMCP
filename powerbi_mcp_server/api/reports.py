"""
Report Operations

Handles download and upload of reports in all formats (PBIR, legacy JSON).
"""

import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


from powerbi_mcp_server.api import PowerBIClient
from powerbi_mcp_server.metadata import MetadataManager

logger = logging.getLogger(__name__)


class ReportOperations:
    """Operations for Power BI reports"""
    
    def __init__(self, client: PowerBIClient, metadata_manager: MetadataManager):
        self.client = client
        self.metadata = metadata_manager
    
    async def download_pbir(
        self,
        workspace_id: str,
        workspace_name: str,
        report_id: str,
        report_name: str,
        target_dir: Path,
        user_email: Optional[str] = None
    ) -> Dict:
        """
        Download report in PBIR format (Power BI Report).

        target_dir is the PROJECT BASE directory.
        Creates: {target_dir}/{report_name}.Report/   (the report files)
                 {target_dir}/{report_name}.pbip       (PBI Desktop entry point, always written)

        If a sibling {report_name}.SemanticModel/ exists PBI Desktop will open both together.

        Returns:
            Dict with download result including directory path and pbip path
        """
        logger.info(f"Downloading PBIR: {report_name} from workspace {workspace_name}")

        # Get definition from Fabric API
        definition = self.client.get_item_definition(workspace_id, report_id)
        parts = (definition.get('definition') or {}).get('parts', [])

        # Build proper .Report folder (PBI Desktop convention)
        report_dir = target_dir / f"{report_name}.Report"

        # Versioning: outside a Git repo, keep a timestamped copy of a previous
        # download instead of silently overwriting it (inside Git, history
        # already protects the previous version).
        version_suffix = None
        if report_dir.is_dir() and any(report_dir.iterdir()) and not self.metadata.is_git_controlled(target_dir):
            version_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = target_dir / f"{report_name}_{version_suffix}.Report"
            report_dir.rename(backup_dir)
            logger.info(f"Preserved previous download as: {backup_dir.name}")

        report_dir.mkdir(parents=True, exist_ok=True)

        # Save each part
        for part in parts:
            part_path = part.get('path')
            payload = part.get('payload')
            payload_type = part.get('payloadType')

            if not part_path or not payload:
                continue

            if payload_type == 'InlineBase64':
                content = base64.b64decode(payload)
            else:
                content = payload.encode('utf-8')

            file_path = report_dir / part_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            logger.debug(f"Saved PBIR part: {part_path}")

        # Report always owns the .pbip entry point
        # (PBI Desktop auto-detects the sibling .SemanticModel folder)
        pbip_path = target_dir / f"{report_name}.pbip"
        pbip_content = {
            "version": "1.0",
            "artifacts": [
                {"report": {"path": f"{report_name}.Report"}}
            ]
        }
        pbip_path.write_text(json.dumps(pbip_content, indent=2), encoding='utf-8')
        logger.info(f"Created/updated .pbip entry point: {pbip_path}")

        # Record metadata
        download_id = self.metadata.record_download(
            artifact_name=report_name,
            artifact_type='Report',
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            local_file_path=report_dir,
            version_suffix=version_suffix,
            user_email=user_email
        )

        logger.info(f"Downloaded PBIR: {report_dir} ({len(parts)} parts)")

        return {
            'success': True,
            'directory_path': str(report_dir),
            'pbip_path': str(pbip_path),
            'format': 'pbir',
            'parts_count': len(parts),
            'versioned': version_suffix is not None,
            'version_suffix': version_suffix,
            'download_id': download_id
        }
    
    @staticmethod
    def _patch_definition_pbir(content: bytes, semantic_model_id: str) -> bytes:
        """
        Rewrite the datasetReference of a definition.pbir to point at a
        published semantic model by ID (byConnection).

        PBIP projects reference their model by relative path (byPath), which
        only resolves when report and model are uploaded together to the same
        workspace. byConnection binds the report to the model's ID instead, so
        the report and its model can live in different workspaces.

        Schema per Microsoft's official docs (definitionProperties/2.0.0):
        https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/report-definition
        byConnection takes a single connectionString field formatted as
        "semanticmodelid=<GUID>" — no other properties are allowed.
        """
        pbir = json.loads(content)
        pbir['datasetReference'] = {
            'byConnection': {
                'connectionString': f'semanticmodelid={semantic_model_id}'
            }
        }
        return json.dumps(pbir, indent=2).encode('utf-8')

    async def upload_pbir(
        self,
        workspace_id: str,
        workspace_name: str,
        directory_path: Path,
        report_name: Optional[str] = None,
        semantic_model_id: Optional[str] = None,
        semantic_model_workspace_id: Optional[str] = None,
        user_email: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> Dict:
        """
        Upload report in PBIR format (Power BI Report)

        Args:
            semantic_model_id: Optional ID to rebind report to different model.
                Patches definition.pbir (byPath -> byConnection) so the model
                can live in a different workspace than the report.
            semantic_model_workspace_id: Workspace where the rebind model lives
                (defaults to the report's workspace; used for metadata tracking)
            folder_path: Optional '/'-separated folder path within the workspace
                to place the report in (created automatically if missing).

        Returns:
            Dict with upload result including asset ID
        """
        if not directory_path.is_dir():
            raise NotADirectoryError(f"PBIR directory not found: {directory_path}")
        
        if report_name is None:
            # Strip .Report suffix if present (folder naming convention)
            name = directory_path.name
            report_name = name[: -len('.Report')] if name.endswith('.Report') else name

        logger.info(f"Uploading PBIR: {report_name} to workspace {workspace_name}")

        # Package PBIR parts — exclude PBI Desktop local files and Fabric platform file
        _EXCLUDE = {'.platform', '.pbi'}
        parts = []
        for file_path in directory_path.rglob('*'):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(directory_path)
            # Skip .platform and anything inside .pbi/
            if relative_path.parts[0] in _EXCLUDE:
                continue
            content = file_path.read_bytes()

            # Handle rebinding: definition.pbir is where the model binding
            # lives in modern PBIR projects (byPath/byConnection)
            if semantic_model_id and str(relative_path).replace('\\', '/') == 'definition.pbir':
                content = self._patch_definition_pbir(content, semantic_model_id)

            # Legacy reports keep the binding as datasetId inside report.json
            if semantic_model_id and relative_path.name == 'report.json':
                report_json = json.loads(content)
                if 'datasetId' in report_json:
                    report_json['datasetId'] = semantic_model_id
                    content = json.dumps(report_json, indent=2).encode('utf-8')

            payload = base64.b64encode(content).decode('utf-8')
            parts.append({
                'path': str(relative_path).replace('\\', '/'),
                'payload': payload,
                'payloadType': 'InlineBase64'
            })

        definition = {
            'format': 'PBIR',
            'parts': parts
        }

        folder_id = self.client.resolve_or_create_folder_path(workspace_id, folder_path)

        # Upsert: update if exists, create if not
        item, created = self.client.upsert_item(
            workspace_id, 'Report', report_name, definition, folder_id=folder_id
        )
        report_id = item.get('id')
        
        # Record metadata
        upload_id = self.metadata.record_upload(
            artifact_name=report_name,
            artifact_type='Report',
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            source_file_path=directory_path,
            asset_id=report_id,
            user_email=user_email
        )
        
        # Track mapping
        self.metadata.track_workspace_mapping(
            local_file_path=directory_path,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            asset_id=report_id,
            asset_name=report_name,
            asset_type='Report'
        )
        
        # Track relationship if rebinding occurred
        if semantic_model_id:
            # Get semantic model name from its workspace (may differ from the report's)
            model_workspace_id = semantic_model_workspace_id or workspace_id
            items = self.client.list_workspace_items(model_workspace_id, 'SemanticModel')
            model_name = next(
                (item['displayName'] for item in items if item['id'] == semantic_model_id),
                'Unknown'
            )
            
            self.metadata.track_report_model_relationship(
                report_id=report_id,
                report_name=report_name,
                semantic_model_id=semantic_model_id,
                semantic_model_name=model_name,
                workspace_id=workspace_id,
                workspace_name=workspace_name
            )
        
        operation = 'created' if created else 'updated'
        logger.info(f"Uploaded PBIR ({operation}): {report_name} (ID: {report_id}, {len(parts)} parts)")

        return {
            'success': True,
            'report_id': report_id,
            'report_name': report_name,
            'format': 'pbir',
            'parts_count': len(parts),
            'operation': operation,
            'rebound_model': semantic_model_id,
            'upload_id': upload_id
        }
    
    async def rebind_report(
        self,
        workspace_id: str,
        workspace_name: str,
        report_name: str,
        semantic_model_id: str,
        semantic_model_name: str,
        semantic_model_workspace_name: str,
        user_email: Optional[str] = None
    ) -> Dict:
        """
        Rebind an existing report to a different semantic model without re-uploading
        its content. The target model can live in a different workspace.

        Returns:
            Dict with rebind result
        """
        reports = self.client.list_workspace_items(workspace_id, 'Report')
        report = next((r for r in reports if r['displayName'] == report_name), None)
        if not report:
            raise ValueError(f"Report no encontrado: {report_name}")

        report_id = report['id']

        self.client.rebind_report(workspace_id, report_id, semantic_model_id)

        self.metadata.track_report_model_relationship(
            report_id=report_id,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
            semantic_model_name=semantic_model_name,
            workspace_id=workspace_id,
            workspace_name=workspace_name
        )

        logger.info(
            f"Rebound report '{report_name}' in '{workspace_name}' to model "
            f"'{semantic_model_name}' in '{semantic_model_workspace_name}'"
        )

        return {
            'success': True,
            'report_id': report_id,
            'report_name': report_name,
            'workspace_name': workspace_name,
            'rebound_model_id': semantic_model_id,
            'rebound_model_name': semantic_model_name,
            'rebound_model_workspace_name': semantic_model_workspace_name
        }

    def find_semantic_models_by_name(
        self,
        workspace_id: str,
        search_name: str
    ) -> List[Dict]:
        """
        Find semantic models in workspace matching name
        
        Returns:
            List of matching semantic models sorted by similarity
        """
        models = self.client.list_workspace_items(workspace_id, 'SemanticModel')
        
        # Exact matches first
        exact_matches = [m for m in models if m['displayName'] == search_name]
        if exact_matches:
            return exact_matches
        
        # Partial matches
        search_lower = search_name.lower()
        partial_matches = [
            m for m in models
            if search_lower in m['displayName'].lower()
        ]
        
        return partial_matches
    
    def detect_format(self, path: Path) -> Optional[str]:
        """
        Detect report format from path
        
        Returns:
            'pbir' or 'json' or None
        """
        if path.is_dir():
            # Check for PBIR indicators
            if (path / 'definition.pbir').exists() or (path / 'report.json').exists():
                return 'pbir'
        elif path.is_file() and path.suffix.lower() == '.json':
            return 'json'
        return None
