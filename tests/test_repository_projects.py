import pytest

from powerbi_mcp_server.metadata.database import MetadataDatabase
from powerbi_mcp_server.metadata.repository import MetadataRepository


def test_schema_migration_is_idempotent(db: MetadataDatabase):
    db.initialize_schema()
    db.initialize_schema()
    with db._db() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM schema_version WHERE version = ?", [db.SCHEMA_VERSION]
        ).fetchone()
    assert rows[0] == 1


def test_database_satisfies_repository_protocol(db: MetadataDatabase):
    assert isinstance(db, MetadataRepository)


def test_predecessor_profile_chain(deploy_config):
    deploy_config.configure_environment("Desarrollo", "ws-dev", stage_order=1)
    deploy_config.configure_environment("Integración", "ws-int", stage_order=2)
    deploy_config.configure_environment("Producción", "ws-prod", stage_order=3)

    assert deploy_config.get_predecessor_profile("Desarrollo") is None
    assert deploy_config.get_predecessor_profile("Integración")["profile_name"] == "Desarrollo"
    assert deploy_config.get_predecessor_profile("Producción")["profile_name"] == "Integración"


def test_predecessor_profile_none_without_stage_order(deploy_config):
    deploy_config.configure_environment("Sandbox", "ws-sandbox")
    assert deploy_config.get_predecessor_profile("Sandbox") is None


def test_configure_environment_rejects_duplicate_stage_order(deploy_config):
    deploy_config.configure_environment("Desarrollo", "ws-dev", stage_order=1)
    with pytest.raises(ValueError):
        deploy_config.configure_environment("Integración", "ws-int", stage_order=1)


def test_configure_environment_update_by_name(deploy_config):
    deploy_config.configure_environment("Desarrollo", "ws-dev", stage_order=1)
    result = deploy_config.configure_environment("Desarrollo", "ws-dev-2", stage_order=1)
    assert result["action"] == "updated"
    profile = deploy_config.db.get_deployment_profile("Desarrollo")
    assert profile["target_workspace_name"] == "ws-dev-2"


def test_list_environments_orders_by_stage_order(deploy_config):
    deploy_config.configure_environment("Producción", "ws-prod", stage_order=3)
    deploy_config.configure_environment("Desarrollo", "ws-dev", stage_order=1)
    deploy_config.configure_environment("Integración", "ws-int", stage_order=2)
    deploy_config.configure_environment("SinOrden", "ws-x")

    names = [e["profile_name"] for e in deploy_config.list_environments()]
    assert names == ["Desarrollo", "Integración", "Producción", "SinOrden"]


def test_project_and_artifact_crud(db: MetadataDatabase):
    project_id = db.create_project("ProyectoX", description="demo")
    assert db.get_project_by_name("ProyectoX")["id"] == project_id

    db.add_project_artifact(project_id, "SemanticModel", "ModeloY")
    db.add_project_artifact(project_id, "Report", "InformeA", rebind_to_artifact_name="ModeloY")

    artifacts = db.list_project_artifacts(project_id)
    assert {(a["artifact_type"], a["artifact_name"]) for a in artifacts} == {
        ("SemanticModel", "ModeloY"), ("Report", "InformeA")
    }

    assert db.remove_project_artifact(project_id, "Report", "InformeA") is True
    assert db.remove_project_artifact(project_id, "Report", "InformeA") is False
    assert len(db.list_project_artifacts(project_id)) == 1


def test_semantic_model_config_scoped_by_profile(db: MetadataDatabase):
    dev_id = db.create_deployment_profile("Desarrollo", stage_order=1)
    prod_id = db.create_deployment_profile("Producción", stage_order=2)

    db.create_semantic_model_config("ModeloY", "ws-dev-id", "ws-dev", profile_id=dev_id, auto_deploy=True)
    db.create_semantic_model_config("ModeloY", "ws-prod-id", "ws-prod", profile_id=prod_id, auto_deploy=False)

    dev_config = db.get_semantic_model_config("ModeloY", profile_id=dev_id)
    prod_config = db.get_semantic_model_config("ModeloY", profile_id=prod_id)
    assert dev_config["target_workspace_name"] == "ws-dev"
    assert prod_config["target_workspace_name"] == "ws-prod"

    # Without profile_id: legacy behaviour, most recently created wins
    latest = db.get_semantic_model_config("ModeloY")
    assert latest["target_workspace_name"] == "ws-prod"


def test_environment_artifact_state_upsert(db: MetadataDatabase):
    project_id = db.create_project("ProyectoX")
    profile_id = db.create_deployment_profile("Desarrollo", stage_order=1)

    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=profile_id, artifact_type="SemanticModel",
        artifact_name="ModeloY", workspace_item_id="item-1", workspace_id="ws-1",
        workspace_name="Desarrollo WS", definition_hash="hash-1", source_profile_id=None,
        last_operation="deploy"
    )
    state = db.get_environment_artifact_state(project_id, profile_id, "SemanticModel", "ModeloY")
    assert state["definition_hash"] == "hash-1"
    assert state["last_operation"] == "deploy"

    # Upsert again should update, not duplicate
    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=profile_id, artifact_type="SemanticModel",
        artifact_name="ModeloY", workspace_item_id="item-1", workspace_id="ws-1",
        workspace_name="Desarrollo WS", definition_hash="hash-2", source_profile_id=None,
        last_operation="promote"
    )
    state = db.get_environment_artifact_state(project_id, profile_id, "SemanticModel", "ModeloY")
    assert state["definition_hash"] == "hash-2"
    assert state["last_operation"] == "promote"
