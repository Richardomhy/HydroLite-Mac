from concurrent.futures import ThreadPoolExecutor

from tests.runtime_helpers import configure_runtime


def test_runtime_database_crud_and_concurrency(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_project_record, get_database_version, get_project_record, initialize_runtime_database
    assert initialize_runtime_database().exists()
    assert get_database_version() == 2
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda i: create_project_record(project_id=f"p{i}", name=f"P{i}", workspace_path=str(tmp_path / f"p{i}"), status="draft"), range(2)))
    assert get_project_record("p1")["name"] == "P1"


def test_corrupt_database_has_clear_error(monkeypatch, tmp_path):
    root = configure_runtime(monkeypatch, tmp_path); root.mkdir()
    (root / "hydrolite_runtime.sqlite3").write_text("broken")
    from hydrolite.runtime_db import initialize_runtime_database
    try: initialize_runtime_database()
    except RuntimeError as exc: assert "corrupt" in str(exc).lower() or "unavailable" in str(exc).lower()
    else: raise AssertionError("corrupt database accepted")


def test_schema_v1_migrates_with_backup_and_preserves_existing_data(monkeypatch, tmp_path):
    import sqlite3
    root = configure_runtime(monkeypatch, tmp_path); root.mkdir()
    database = root / "hydrolite_runtime.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_migrations VALUES(1, 'before');
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, name TEXT, display_name TEXT, workspace_path TEXT UNIQUE, project_yaml TEXT, status TEXT, created_at TEXT, updated_at TEXT, last_opened_at TEXT, data_quality_status TEXT, workflow_readiness TEXT, checksum TEXT, archived INTEGER DEFAULT 0, warnings TEXT);
        INSERT INTO projects(project_id, name, workspace_path, status) VALUES('existing', 'Existing', '/tmp/existing', 'ready');
        CREATE TABLE project_versions(version_id TEXT PRIMARY KEY, project_id TEXT, checksum TEXT, created_at TEXT, metadata TEXT);
        INSERT INTO project_versions VALUES('legacy_v1', 'existing', 'abc', 'before', '{"source":"legacy"}');
        """
    )
    connection.commit(); connection.close()
    from hydrolite.runtime_db import get_database_version, get_migration_backup_path, get_project_record, get_project_version_record, initialize_runtime_database
    initialize_runtime_database()
    assert get_database_version() == 2
    assert get_migration_backup_path() and get_migration_backup_path().exists()
    assert get_project_record("existing")["name"] == "Existing"
    assert get_project_version_record("legacy_v1")["checksum"] == "abc"
