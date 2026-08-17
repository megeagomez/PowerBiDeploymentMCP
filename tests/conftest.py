import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from powerbi_mcp_server.metadata.database import MetadataDatabase
from powerbi_mcp_server.metadata.deployment_config import DeploymentConfigManager


@pytest.fixture
def db(tmp_path) -> MetadataDatabase:
    database = MetadataDatabase(db_path=tmp_path / "test.duckdb")
    database.initialize_schema()
    return database


@pytest.fixture
def deploy_config(db) -> DeploymentConfigManager:
    return DeploymentConfigManager(db)
