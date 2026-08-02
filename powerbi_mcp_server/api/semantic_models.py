"""
Semantic Model Operations

Handles download and upload of semantic models in all formats (PBIX, PBIP).
"""

import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from powerbi_mcp_server.api import PowerBIClient
from powerbi_mcp_server.metadata import MetadataManager

logger = logging.getLogger(__name__)


class SemanticModelOperations:
    """Operations for Power BI semantic models"""
    
    def __init__(self, client: PowerBIClient, metadata_manager: MetadataManager):
        self.client = client
        self.metadata = metadata_manager
    
    # NOTE: PBIX download for semantic models was removed — the Power BI REST
    # API has no dataset-level export endpoint (export is report-level only).
    # Semantic models are downloaded as PBIP via the Fabric definition API.

    async def download_pbip(
        self,
        workspace_id: str,
        workspace_name: str,
        dataset_id: str,
        dataset_name: str,
        target_dir: Path,
        user_email: Optional[str] = None
    ) -> Dict:
        """
        Download semantic model in PBIP format (Power BI Project).

        target_dir is the PROJECT BASE directory.
        Creates: {target_dir}/{dataset_name}.SemanticModel/  (the model files)
                 {target_dir}/{dataset_name}.pbip             (PBI Desktop entry point, if absent)

        Returns:
            Dict with download result including directory path and pbip path
        """
        logger.info(f"Downloading PBIP: {dataset_name} from workspace {workspace_name}")

        # Get definition from Fabric API
        definition = self.client.get_item_definition(workspace_id, dataset_id)
        parts = (definition.get('definition') or {}).get('parts', [])

        # Build proper .SemanticModel folder (PBI Desktop convention)
        sm_dir = target_dir / f"{dataset_name}.SemanticModel"

        # Versioning: outside a Git repo, keep a timestamped copy of a previous
        # download instead of silently overwriting it (inside Git, history
        # already protects the previous version).
        version_suffix = None
        if sm_dir.is_dir() and any(sm_dir.iterdir()) and not self.metadata.is_git_controlled(target_dir):
            version_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = target_dir / f"{dataset_name}_{version_suffix}.SemanticModel"
            sm_dir.rename(backup_dir)
            logger.info(f"Preserved previous download as: {backup_dir.name}")

        sm_dir.mkdir(parents=True, exist_ok=True)

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

            file_path = sm_dir / part_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            logger.debug(f"Saved PBIP part: {part_path}")

        # Create .pbip entry point only if one doesn't exist yet
        # (a report download with the same name will own/overwrite it later)
        pbip_path = target_dir / f"{dataset_name}.pbip"
        if not pbip_path.exists():
            pbip_content = {
                "version": "1.0",
                "artifacts": [
                    {"semanticModel": {"path": f"{dataset_name}.SemanticModel"}}
                ]
            }
            pbip_path.write_text(json.dumps(pbip_content, indent=2), encoding='utf-8')
            logger.info(f"Created .pbip entry point: {pbip_path}")

        # Record metadata
        download_id = self.metadata.record_download(
            artifact_name=dataset_name,
            artifact_type='SemanticModel',
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            local_file_path=sm_dir,
            version_suffix=version_suffix,
            user_email=user_email
        )

        logger.info(f"Downloaded PBIP: {sm_dir} ({len(parts)} parts)")

        return {
            'success': True,
            'directory_path': str(sm_dir),
            'pbip_path': str(pbip_path),
            'format': 'pbip',
            'parts_count': len(parts),
            'versioned': version_suffix is not None,
            'version_suffix': version_suffix,
            'download_id': download_id
        }
    
    async def upload_pbix(
        self,
        workspace_id: str,
        workspace_name: str,
        file_path: Path,
        dataset_name: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> Dict:
        """
        Upload semantic model in PBIX format
        
        Returns:
            Dict with upload result including asset ID
        """
        if not file_path.exists():
            raise FileNotFoundError(f"PBIX file not found: {file_path}")
        
        if dataset_name is None:
            dataset_name = file_path.stem
        
        logger.info(f"Uploading PBIX: {dataset_name} to workspace {workspace_name}")
        
        # Upload via API
        result = self.client.import_pbix(workspace_id, str(file_path), dataset_name)
        dataset_id = result.get('id')
        
        # Record metadata
        upload_id = self.metadata.record_upload(
            artifact_name=dataset_name,
            artifact_type='SemanticModel',
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            source_file_path=file_path,
            asset_id=dataset_id,
            user_email=user_email
        )
        
        # Track mapping
        self.metadata.track_workspace_mapping(
            local_file_path=file_path,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            asset_id=dataset_id,
            asset_name=dataset_name,
            asset_type='SemanticModel'
        )
        
        logger.info(f"Uploaded PBIX: {dataset_name} (ID: {dataset_id})")
        
        return {
            'success': True,
            'dataset_id': dataset_id,
            'dataset_name': dataset_name,
            'format': 'pbix',
            'upload_id': upload_id
        }
    
    async def upload_pbip(
        self,
        workspace_id: str,
        workspace_name: str,
        directory_path: Path,
        dataset_name: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> Dict:
        """
        Upload semantic model in PBIP format (Power BI Project)
        
        Returns:
            Dict with upload result including asset ID
        """
        if not directory_path.is_dir():
            raise NotADirectoryError(f"PBIP directory not found: {directory_path}")
        
        if dataset_name is None:
            # Strip .SemanticModel suffix if present (folder naming convention)
            name = directory_path.name
            dataset_name = name[: -len('.SemanticModel')] if name.endswith('.SemanticModel') else name

        logger.info(f"Uploading PBIP: {dataset_name} to workspace {workspace_name}")

        # Package PBIP parts — exclude PBI Desktop local files and Fabric platform file
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
            payload = base64.b64encode(content).decode('utf-8')
            parts.append({
                'path': str(relative_path).replace('\\', '/'),
                'payload': payload,
                'payloadType': 'InlineBase64'
            })

        definition = {
            'format': 'TMDL',
            'parts': parts
        }

        # Upsert: update if exists, create if not
        item, created = self.client.upsert_item(workspace_id, 'SemanticModel', dataset_name, definition)
        dataset_id = item.get('id')
        
        # Record metadata
        upload_id = self.metadata.record_upload(
            artifact_name=dataset_name,
            artifact_type='SemanticModel',
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            source_file_path=directory_path,
            asset_id=dataset_id,
            user_email=user_email
        )
        
        # Track mapping
        self.metadata.track_workspace_mapping(
            local_file_path=directory_path,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            asset_id=dataset_id,
            asset_name=dataset_name,
            asset_type='SemanticModel'
        )
        
        operation = 'created' if created else 'updated'
        logger.info(f"Uploaded PBIP ({operation}): {dataset_name} (ID: {dataset_id}, {len(parts)} parts)")

        return {
            'success': True,
            'dataset_id': dataset_id,
            'dataset_name': dataset_name,
            'format': 'pbip',
            'parts_count': len(parts),
            'operation': operation,
            'upload_id': upload_id
        }
    
    def detect_format(self, path: Path) -> Optional[str]:
        """
        Detect semantic model format from path.

        Returns:
            'pbix' or 'pbip' or None
        """
        if path.is_file() and path.suffix.lower() == '.pbix':
            return 'pbix'
        elif path.is_dir():
            # Folder name convention created by download_pbip
            if path.name.endswith('.SemanticModel'):
                return 'pbip'
            # Content-based detection
            if (path / 'item.metadata.json').exists() or (path / 'model.bim').exists():
                return 'pbip'
        return None
