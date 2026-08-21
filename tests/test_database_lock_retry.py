"""
Tests for MetadataDatabase's retry-on-lock-conflict behavior in _db().

DuckDB allows only one process to hold a given database file open at a
time. This package can be launched as more than one independent OS process
against the same metadata.duckdb (e.g. Claude Desktop's normal chat session
plus a separate copy it starts for Cowork/Code sessions) — _db() must ride
out a transient duckdb.IOException from that race instead of crashing.
"""

import subprocess
import sys
import time

import duckdb
import pytest

from powerbi_mcp_server.metadata import database as database_module
from powerbi_mcp_server.metadata.database import MetadataDatabase


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Keep the mocked-retry tests fast — no need to wait out real backoff."""
    monkeypatch.setattr(database_module.time, "sleep", lambda _seconds: None)


def test_db_retries_and_succeeds_after_transient_lock(tmp_path, monkeypatch):
    db = MetadataDatabase(db_path=tmp_path / "test.duckdb")
    real_connect = duckdb.connect
    calls = {"count": 0}

    def flaky_connect(path):
        calls["count"] += 1
        if calls["count"] < 3:
            raise duckdb.IOException("Cannot open file: locked by another process")
        return real_connect(path)

    monkeypatch.setattr(database_module.duckdb, "connect", flaky_connect)

    db.initialize_schema()

    assert calls["count"] == 3


def test_db_gives_up_after_exhausting_retries(tmp_path, monkeypatch):
    db = MetadataDatabase(db_path=tmp_path / "test.duckdb")
    calls = {"count": 0}

    def always_locked(path):
        calls["count"] += 1
        raise duckdb.IOException("Cannot open file: locked by another process")

    monkeypatch.setattr(database_module.duckdb, "connect", always_locked)

    with pytest.raises(duckdb.IOException):
        db.get_deployment_stats()

    assert calls["count"] == database_module._LOCK_RETRY_ATTEMPTS


def test_db_survives_real_cross_process_lock(tmp_path):
    """
    Integration check with a genuine second OS process holding the file
    open, not a mock — proves the retry loop works against DuckDB's actual
    file-locking behavior, not just our assumption about the exception type.
    """
    db_path = tmp_path / "cross_process.duckdb"

    holder_code = (
        "import duckdb, time\n"
        f"conn = duckdb.connect(r'{db_path}')\n"
        "conn.execute('CREATE TABLE IF NOT EXISTS t (i INTEGER)')\n"
        "time.sleep(2)\n"
        "conn.close()\n"
    )
    holder = subprocess.Popen([sys.executable, "-c", holder_code])
    try:
        time.sleep(0.5)  # let the holder acquire the lock first
        db = MetadataDatabase(db_path=db_path)
        db.initialize_schema()  # must not raise — should retry until the holder releases
    finally:
        holder.wait(timeout=10)
