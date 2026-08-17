"""
Metadata repository interface

Defines the backend-agnostic contract used by the new project/environment
promotion code (ProjectManager, environment-hierarchy helpers in
DeploymentConfigManager). MetadataDatabase (DuckDB) satisfies this protocol
structurally today; a future SQL Server-backed implementation only needs to
provide the same methods without any change to callers.

Existing methods on MetadataDatabase that predate this interface (downloads,
uploads, workspace_mappings, report_model_relationships, the single-artifact
semantic_model_configs/report_configs CRUD) are intentionally NOT included
here — retrofitting them is a natural follow-up once a second backend is
actually being built, not a prerequisite for this feature.
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class MetadataRepository(Protocol):
    # --- environment hierarchy (profiles) ---
    def create_deployment_profile(
        self,
        profile_name: str,
        target_workspace_id: Optional[str] = None,
        target_workspace_name: Optional[str] = None,
        environment_type: str = 'development',
        description: Optional[str] = None,
        stage_order: Optional[int] = None
    ) -> int: ...

    def update_deployment_profile(
        self,
        profile_name: str,
        target_workspace_id: Optional[str] = None,
        target_workspace_name: Optional[str] = None,
        stage_order: Optional[int] = None,
        environment_type: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool: ...

    def get_deployment_profile(self, profile_name: str) -> Optional[Dict]: ...

    def get_deployment_profile_by_id(self, profile_id: int) -> Optional[Dict]: ...

    def list_deployment_profiles(self) -> List[Dict]: ...

    # --- projects ---
    def create_project(self, project_name: str, description: Optional[str] = None) -> int: ...

    def get_project_by_name(self, project_name: str) -> Optional[Dict]: ...

    def list_projects(self) -> List[Dict]: ...

    def add_project_artifact(
        self,
        project_id: int,
        artifact_type: str,
        artifact_name: str,
        rebind_to_artifact_name: Optional[str] = None,
        sequence_order: Optional[int] = None,
        notes: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> int: ...

    def list_project_artifacts(self, project_id: int) -> List[Dict]: ...

    def remove_project_artifact(self, project_id: int, artifact_type: str, artifact_name: str) -> bool: ...

    # --- per-project workspace overrides ---
    def upsert_project_environment_workspace(
        self,
        project_id: int,
        profile_id: int,
        artifact_type: Optional[str],
        workspace_id: str,
        workspace_name: str
    ) -> int: ...

    def list_project_environment_workspaces(
        self, project_id: int, profile_id: Optional[int] = None
    ) -> List[Dict]: ...

    # --- environment current-state / drift ---
    def get_environment_artifact_state(
        self, project_id: int, profile_id: int, artifact_type: str, artifact_name: str
    ) -> Optional[Dict]: ...

    def upsert_environment_artifact_state(
        self,
        project_id: int,
        profile_id: int,
        artifact_type: str,
        artifact_name: str,
        workspace_item_id: Optional[str],
        workspace_id: Optional[str],
        workspace_name: Optional[str],
        definition_hash: Optional[str],
        source_profile_id: Optional[int],
        last_operation: str,
        promotion_event_id: Optional[int] = None,
        updated_by: Optional[str] = None
    ) -> None: ...

    # --- promotion audit ---
    def record_promotion_event(
        self,
        project_id: int,
        operation: str,
        to_profile_id: int,
        from_profile_id: Optional[int] = None,
        artifact_summary: Optional[str] = None,
        drift_detected: bool = False,
        drift_confirmed: bool = False,
        status: str = 'success',
        error_message: Optional[str] = None,
        initiated_by: Optional[str] = None
    ) -> int: ...
