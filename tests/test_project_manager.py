import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from powerbi_mcp_server.metadata.project_manager import ProjectManager


def _make_project(db, deploy_config):
    project_id = db.create_project("ProyectoX")
    db.add_project_artifact(project_id, "SemanticModel", "ModeloY")
    db.add_project_artifact(project_id, "Report", "InformeA", rebind_to_artifact_name="ModeloY")
    return project_id


def _make_pm(db, deploy_config, client):
    semantic_models = MagicMock()
    semantic_models.upload_pbip = AsyncMock(return_value={"dataset_id": "deployed-model-id"})
    reports = MagicMock()
    reports.upload_pbir = AsyncMock(return_value={"report_id": "deployed-report-id"})
    metadata = MagicMock()
    pm = ProjectManager(db, deploy_config, metadata, client, semantic_models, reports)
    return pm, semantic_models, reports, metadata


def test_deploy_project_orders_model_before_report_and_records_state(db, deploy_config, tmp_path):
    _make_project(db, deploy_config)
    deploy_config.configure_environment("Desarrollo", "ws-dev", target_workspace_id="ws-dev-id", stage_order=1)

    client = MagicMock()
    client.get_item_definition = MagicMock(return_value={"definition": {"parts": [{"path": "x", "payload": "y"}]}})

    pm, semantic_models, reports, _ = _make_pm(db, deploy_config, client)

    calls = []
    async def fake_upload_pbip(*a, **k):
        calls.append("model")
        return {"dataset_id": "deployed-model-id"}
    async def fake_upload_pbir(*a, **k):
        calls.append("report")
        return {"report_id": "deployed-report-id"}
    semantic_models.upload_pbip = fake_upload_pbip
    reports.upload_pbir = fake_upload_pbir

    result = asyncio.run(pm.deploy_project("ProyectoX", "Desarrollo", tmp_path))

    assert result["success"] is True
    assert calls == ["model", "report"]

    project = db.get_project_by_name("ProyectoX")
    profile = db.get_deployment_profile("Desarrollo")
    model_state = db.get_environment_artifact_state(project["id"], profile["id"], "SemanticModel", "ModeloY")
    assert model_state["last_operation"] == "deploy"
    assert model_state["source_profile_id"] is None


def _wire_promote_mocks(source_ws_id, target_ws_id, target_state_item_ids=None):
    target_state_item_ids = target_state_item_ids or {}

    def list_workspace_items(workspace_id, item_type):
        if workspace_id == source_ws_id:
            if item_type == "SemanticModel":
                return [{"displayName": "ModeloY", "id": "src-model-id"}]
            if item_type == "Report":
                return [{"displayName": "InformeA", "id": "src-report-id"}]
        if workspace_id == target_ws_id:
            items = []
            if "SemanticModel" in target_state_item_ids:
                items.append({"displayName": "ModeloY", "id": target_state_item_ids["SemanticModel"]})
            if "Report" in target_state_item_ids:
                items.append({"displayName": "InformeA", "id": target_state_item_ids["Report"]})
            return items
        return []

    def get_item_definition(workspace_id, item_id):
        return {"definition": {"parts": [{"path": "x", "payload": f"{item_id}-payload"}]}}

    def upsert_item(workspace_id, item_type, display_name, definition, folder_id=None):
        return ({"id": f"target-{display_name}-id", "folder_id": folder_id}, True)

    def resolve_or_create_folder_path(workspace_id, folder_path):
        if not folder_path:
            return None
        return f"folder-id:{workspace_id}:{folder_path}"

    client = MagicMock()
    client.list_workspace_items = MagicMock(side_effect=list_workspace_items)
    client.get_item_definition = MagicMock(side_effect=get_item_definition)
    client.upsert_item = MagicMock(side_effect=upsert_item)
    client.resolve_or_create_folder_path = MagicMock(side_effect=resolve_or_create_folder_path)
    client.rebind_report = MagicMock()
    return client


def test_promote_project_no_prior_state_succeeds_without_confirmation(db, deploy_config):
    _make_project(db, deploy_config)
    deploy_config.configure_environment("Integración", "ws-int", target_workspace_id="ws-int-id", stage_order=1)
    deploy_config.configure_environment("Producción", "ws-prod", target_workspace_id="ws-prod-id", stage_order=2)

    client = _wire_promote_mocks("ws-int-id", "ws-prod-id")
    pm, _, _, metadata = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.promote_project("ProyectoX", "Producción"))

    assert result["success"] is True
    assert result["source_environment"] == "Integración"
    assert result["target_environment"] == "Producción"

    upsert_calls = [c.args[1] for c in client.upsert_item.call_args_list]
    assert upsert_calls == ["SemanticModel", "Report"]

    client.rebind_report.assert_called_once()
    metadata.track_report_model_relationship.assert_called_once()


def test_promote_project_blocks_on_drift_without_side_effects(db, deploy_config):
    project_id = _make_project(db, deploy_config)
    deploy_config.configure_environment("Integración", "ws-int", target_workspace_id="ws-int-id", stage_order=1)
    prod = deploy_config.configure_environment("Producción", "ws-prod", target_workspace_id="ws-prod-id", stage_order=2)

    # Simulate a prior emergency `deploy` straight into Producción (bypassing the chain)
    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=prod["id"], artifact_type="SemanticModel",
        artifact_name="ModeloY", workspace_item_id="existing-model-id", workspace_id="ws-prod-id",
        workspace_name="ws-prod", definition_hash="existing-hash", source_profile_id=None,
        last_operation="deploy"
    )
    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=prod["id"], artifact_type="Report",
        artifact_name="InformeA", workspace_item_id="existing-report-id", workspace_id="ws-prod-id",
        workspace_name="ws-prod", definition_hash="existing-hash", source_profile_id=None,
        last_operation="deploy"
    )

    client = _wire_promote_mocks(
        "ws-int-id", "ws-prod-id",
        target_state_item_ids={"SemanticModel": "existing-model-id", "Report": "existing-report-id"}
    )
    pm, _, _, _ = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.promote_project("ProyectoX", "Producción"))

    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert len(result["drift"]) == 2
    client.upsert_item.assert_not_called()
    client.rebind_report.assert_not_called()


def test_promote_project_confirm_drift_proceeds(db, deploy_config):
    project_id = _make_project(db, deploy_config)
    deploy_config.configure_environment("Integración", "ws-int", target_workspace_id="ws-int-id", stage_order=1)
    prod = deploy_config.configure_environment("Producción", "ws-prod", target_workspace_id="ws-prod-id", stage_order=2)

    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=prod["id"], artifact_type="SemanticModel",
        artifact_name="ModeloY", workspace_item_id="existing-model-id", workspace_id="ws-prod-id",
        workspace_name="ws-prod", definition_hash="existing-hash", source_profile_id=None,
        last_operation="deploy"
    )
    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=prod["id"], artifact_type="Report",
        artifact_name="InformeA", workspace_item_id="existing-report-id", workspace_id="ws-prod-id",
        workspace_name="ws-prod", definition_hash="existing-hash", source_profile_id=None,
        last_operation="deploy"
    )

    client = _wire_promote_mocks(
        "ws-int-id", "ws-prod-id",
        target_state_item_ids={"SemanticModel": "existing-model-id", "Report": "existing-report-id"}
    )
    pm, _, _, _ = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.promote_project("ProyectoX", "Producción", confirm_drift=True))

    assert result["success"] is True
    assert result["drift_confirmed"] is True
    client.upsert_item.assert_called()

    with db._db() as conn:
        events = conn.execute("SELECT drift_detected, drift_confirmed, status FROM promotion_events").fetchall()
    assert events[-1] == (True, True, "success")


def test_promote_project_raises_without_predecessor(db, deploy_config):
    _make_project(db, deploy_config)
    deploy_config.configure_environment("Desarrollo", "ws-dev", target_workspace_id="ws-dev-id", stage_order=1)

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())

    with pytest.raises(ValueError):
        asyncio.run(pm.promote_project("ProyectoX", "Desarrollo"))


def test_promote_project_resolves_folder_and_passes_to_upsert_item(db, deploy_config):
    project_id = db.create_project("ProyectoX")
    db.add_project_artifact(project_id, "SemanticModel", "ModeloY", folder_path="Ventas/Modelos")
    db.add_project_artifact(project_id, "Report", "InformeA", rebind_to_artifact_name="ModeloY")
    deploy_config.configure_environment("Integración", "ws-int", target_workspace_id="ws-int-id", stage_order=1)
    deploy_config.configure_environment("Producción", "ws-prod", target_workspace_id="ws-prod-id", stage_order=2)

    client = _wire_promote_mocks("ws-int-id", "ws-prod-id")
    pm, _, _, _ = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.promote_project("ProyectoX", "Producción"))

    assert result["success"] is True
    client.resolve_or_create_folder_path.assert_any_call("ws-prod-id", "Ventas/Modelos")
    client.resolve_or_create_folder_path.assert_any_call("ws-prod-id", None)

    model_call = next(c for c in client.upsert_item.call_args_list if c.args[1] == "SemanticModel")
    assert model_call.kwargs["folder_id"] == "folder-id:ws-prod-id:Ventas/Modelos"


def test_locate_artifact_dir_flat_by_default(db, deploy_config, tmp_path):
    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())
    found_dir, folder_path = pm._locate_artifact_dir(tmp_path, "ModeloY", ".SemanticModel", False)
    assert found_dir == tmp_path / "ModeloY.SemanticModel"
    assert folder_path is None


def test_locate_artifact_dir_derives_folder_from_nested_layout(db, deploy_config, tmp_path):
    nested = tmp_path / "Modelos" / "ModeloY.SemanticModel"
    nested.mkdir(parents=True)

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())
    found_dir, folder_path = pm._locate_artifact_dir(tmp_path, "ModeloY", ".SemanticModel", True)

    assert found_dir == nested
    assert folder_path == "Modelos"


def test_locate_artifact_dir_raises_on_ambiguous_matches(db, deploy_config, tmp_path):
    (tmp_path / "A" / "ModeloY.SemanticModel").mkdir(parents=True)
    (tmp_path / "B" / "ModeloY.SemanticModel").mkdir(parents=True)

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())
    with pytest.raises(ValueError):
        pm._locate_artifact_dir(tmp_path, "ModeloY", ".SemanticModel", True)


def test_deploy_project_respect_local_structure_explicit_folder_wins(db, deploy_config, tmp_path):
    project_id = db.create_project("ProyectoX")
    db.add_project_artifact(project_id, "SemanticModel", "ModeloY")
    db.add_project_artifact(
        project_id, "Report", "InformeA", rebind_to_artifact_name="ModeloY", folder_path="Manual/Folder"
    )
    deploy_config.configure_environment("Desarrollo", "ws-dev", target_workspace_id="ws-dev-id", stage_order=1)

    (tmp_path / "Modelos" / "ModeloY.SemanticModel").mkdir(parents=True)
    (tmp_path / "Informes" / "InformeA.Report").mkdir(parents=True)

    client = MagicMock()
    client.get_item_definition = MagicMock(return_value={"definition": {"parts": []}})
    pm, semantic_models, reports, _ = _make_pm(db, deploy_config, client)

    captured = {}

    async def fake_upload_pbip(*a, **k):
        captured["model_folder"] = k.get("folder_path")
        return {"dataset_id": "deployed-model-id"}

    async def fake_upload_pbir(*a, **k):
        captured["report_folder"] = k.get("folder_path")
        return {"report_id": "deployed-report-id"}

    semantic_models.upload_pbip = fake_upload_pbip
    reports.upload_pbir = fake_upload_pbir

    result = asyncio.run(pm.deploy_project("ProyectoX", "Desarrollo", tmp_path, respect_local_structure=True))

    assert result["success"] is True
    assert captured["model_folder"] == "Modelos"       # derived from local layout
    assert captured["report_folder"] == "Manual/Folder"  # explicit config wins over "Informes"


def test_get_deployment_structure_shape(db, deploy_config):
    project_id = db.create_project("ProyectoX", description="Proyecto de ventas")
    db.add_project_artifact(project_id, "SemanticModel", "ModeloY", folder_path="Ventas/Modelos")
    db.add_project_artifact(project_id, "Report", "InformeA", rebind_to_artifact_name="ModeloY")
    dev = deploy_config.configure_environment("Desarrollo", "ws-dev", target_workspace_id="ws-dev-id", stage_order=1)
    deploy_config.configure_environment("Producción", "ws-prod", target_workspace_id="ws-prod-id", stage_order=2)

    db.upsert_environment_artifact_state(
        project_id=project_id, profile_id=dev["id"], artifact_type="SemanticModel",
        artifact_name="ModeloY", workspace_item_id="item-1", workspace_id="ws-dev-id",
        workspace_name="ws-dev", definition_hash="h1", source_profile_id=None, last_operation="deploy"
    )

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())
    structure = pm.get_deployment_structure("ProyectoX")

    assert structure["project_name"] == "ProyectoX"
    assert structure["description"] == "Proyecto de ventas"
    assert {a["artifact_name"]: a["folder_path"] for a in structure["artifacts"]} == {
        "ModeloY": "Ventas/Modelos", "InformeA": None
    }

    env_by_name = {e["profile_name"]: e for e in structure["environments"]}
    assert list(env_by_name.keys()) == ["Desarrollo", "Producción"]

    dev_model = next(a for a in env_by_name["Desarrollo"]["artifacts"] if a["artifact_name"] == "ModeloY")
    assert dev_model["current_state"]["last_operation"] == "deploy"
    assert dev_model["target_folder_path"] == "Ventas/Modelos"

    prod_model = next(a for a in env_by_name["Producción"]["artifacts"] if a["artifact_name"] == "ModeloY")
    assert prod_model["current_state"] is None


# ========== Workspace creation ==========

def _wire_workspace_mocks(existing_by_name=None):
    existing_by_name = dict(existing_by_name or {})
    created = []

    def get_workspace_by_name(name):
        return existing_by_name.get(name)

    def create_workspace(name, capacity_id=None):
        ws = {"id": f"ws-{name}", "name": name}
        existing_by_name[name] = ws
        created.append((name, capacity_id))
        return ws

    client = MagicMock()
    client.get_workspace_by_name = MagicMock(side_effect=get_workspace_by_name)
    client.create_workspace = MagicMock(side_effect=create_workspace)
    client._created = created
    return client


def test_resolve_target_workspace_precedence(db, deploy_config):
    project_id = db.create_project("ProyectoX")
    deploy_config.configure_environment("Desarrollo", "ws-global", target_workspace_id="ws-global-id", stage_order=1)
    profile = db.get_deployment_profile("Desarrollo")

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())

    # No overrides: falls back to the environment's own workspace
    resolved = pm._resolve_target_workspace(project_id, profile, "SemanticModel")
    assert resolved == {"workspace_id": "ws-global-id", "workspace_name": "ws-global"}

    # Combined override applies to both types
    db.upsert_project_environment_workspace(project_id, profile["id"], None, "ws-combined-id", "ws-combined")
    resolved = pm._resolve_target_workspace(project_id, profile, "Report")
    assert resolved == {"workspace_id": "ws-combined-id", "workspace_name": "ws-combined"}

    # Type-specific override wins over the combined one
    db.upsert_project_environment_workspace(project_id, profile["id"], "SemanticModel", "ws-model-id", "ws-model")
    assert pm._resolve_target_workspace(project_id, profile, "SemanticModel") == {
        "workspace_id": "ws-model-id", "workspace_name": "ws-model"
    }
    assert pm._resolve_target_workspace(project_id, profile, "Report") == {
        "workspace_id": "ws-combined-id", "workspace_name": "ws-combined"
    }


def test_configure_project_workspace_creates_when_missing(db, deploy_config):
    db.create_project("ProyectoX")
    deploy_config.configure_environment("dev", stage_order=1)

    client = _wire_workspace_mocks()
    pm, _, _, _ = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.configure_project_workspace("ProyectoX", "dev", "Ventas_semantic_dev", artifact_type="model"))

    assert result["created"] is True
    assert result["artifact_type"] == "SemanticModel"
    client.create_workspace.assert_called_once_with("Ventas_semantic_dev", capacity_id=None)

    project = db.get_project_by_name("ProyectoX")
    profile = db.get_deployment_profile("dev")
    overrides = db.list_project_environment_workspaces(project["id"], profile["id"])
    assert len(overrides) == 1
    assert overrides[0]["workspace_name"] == "Ventas_semantic_dev"
    assert overrides[0]["artifact_type"] == "SemanticModel"


def test_configure_project_workspace_reuses_existing(db, deploy_config):
    db.create_project("ProyectoX")
    deploy_config.configure_environment("dev", stage_order=1)

    client = _wire_workspace_mocks(existing_by_name={"Ventas_semantic_dev": {"id": "already-there", "name": "Ventas_semantic_dev"}})
    pm, _, _, _ = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.configure_project_workspace("ProyectoX", "dev", "Ventas_semantic_dev", artifact_type="model"))

    assert result["created"] is False
    client.create_workspace.assert_not_called()


def test_auto_provision_project_workspaces_creates_envs_and_six_workspaces(db, deploy_config):
    db.create_project("Ventas")
    client = _wire_workspace_mocks()
    pm, _, _, _ = _make_pm(db, deploy_config, client)

    result = asyncio.run(pm.auto_provision_project_workspaces("Ventas"))

    assert result["environments_created"] == ["dev", "acc", "prod"]
    assert db.get_deployment_profile("dev")["stage_order"] == 1
    assert db.get_deployment_profile("acc")["stage_order"] == 2
    assert db.get_deployment_profile("prod")["stage_order"] == 3

    names = sorted(w["workspace_name"] for w in result["workspaces"])
    assert names == sorted([
        "Ventas_semantic_dev", "Ventas_reports_dev",
        "Ventas_semantic_acc", "Ventas_reports_acc",
        "Ventas_semantic", "Ventas_reports"
    ])

    project = db.get_project_by_name("Ventas")
    dev_profile = db.get_deployment_profile("dev")
    overrides = db.list_project_environment_workspaces(project["id"], dev_profile["id"])
    assert len(overrides) == 2


def test_deploy_project_routes_split_type_workspaces(db, deploy_config, tmp_path):
    project_id = db.create_project("ProyectoX")
    db.add_project_artifact(project_id, "SemanticModel", "ModeloY")
    db.add_project_artifact(project_id, "Report", "InformeA", rebind_to_artifact_name="ModeloY")
    profile = deploy_config.configure_environment("Desarrollo", stage_order=1)

    db.upsert_project_environment_workspace(project_id, profile["id"], "SemanticModel", "ws-model-id", "Ventas_semantic_dev")
    db.upsert_project_environment_workspace(project_id, profile["id"], "Report", "ws-report-id", "Ventas_reports_dev")

    client = MagicMock()
    client.get_item_definition = MagicMock(return_value={"definition": {"parts": []}})
    pm, semantic_models, reports, _ = _make_pm(db, deploy_config, client)

    captured = {}

    async def fake_upload_pbip(*a, **k):
        captured["model_ws"] = k.get("workspace_id")
        return {"dataset_id": "deployed-model-id"}

    async def fake_upload_pbir(*a, **k):
        captured["report_ws"] = k.get("workspace_id")
        return {"report_id": "deployed-report-id"}

    semantic_models.upload_pbip = fake_upload_pbip
    reports.upload_pbir = fake_upload_pbir

    result = asyncio.run(pm.deploy_project("ProyectoX", "Desarrollo", tmp_path))

    assert result["success"] is True
    assert captured["model_ws"] == "ws-model-id"
    assert captured["report_ws"] == "ws-report-id"


def test_deploy_project_fails_clearly_without_any_workspace(db, deploy_config, tmp_path):
    db.create_project("ProyectoX")
    db.add_project_artifact(db.get_project_by_name("ProyectoX")["id"], "SemanticModel", "ModeloY")
    deploy_config.configure_environment("Desarrollo", stage_order=1)  # no workspace at all

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())

    with pytest.raises(ValueError):
        asyncio.run(pm.deploy_project("ProyectoX", "Desarrollo", tmp_path))


# ========== Deployment tree ==========

def test_render_deployment_tree_shows_env_folder_and_artifact(db, deploy_config):
    project_id = db.create_project("Ventas", description="Proyecto de ventas")
    db.add_project_artifact(project_id, "SemanticModel", "ModeloVentas", folder_path="Modelos")
    deploy_config.configure_environment("dev", target_workspace_name="Ventas_semantic_dev", stage_order=1)

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())
    tree = pm.render_deployment_tree("Ventas")

    assert "Ventas" in tree
    assert "|-- dev" in tree
    assert "|-- Modelos" in tree
    assert "ModeloVentas" in tree
    assert "Ventas_semantic_dev" in tree
    assert "sin desplegar" in tree


def test_render_deployment_tree_all_projects_when_no_name_given(db, deploy_config):
    db.create_project("Ventas")
    db.create_project("RRHH")

    pm, _, _, _ = _make_pm(db, deploy_config, MagicMock())
    tree = pm.render_deployment_tree()

    assert "Ventas" in tree
    assert "RRHH" in tree
