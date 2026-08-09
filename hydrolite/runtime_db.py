from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import stat
from typing import Any, Iterator

from hydrolite.runtime_paths import get_runtime_db_path


SCHEMA_VERSION = 2
TABLE_COLUMNS = {
    "projects": ("project_id", "name", "display_name", "workspace_path", "project_yaml", "status", "created_at", "updated_at", "last_opened_at", "data_quality_status", "workflow_readiness", "checksum", "archived", "warnings"),
    "project_versions": ("project_version_id", "project_id", "version_number", "parent_version_id", "created_at", "created_by", "description", "scenario_ids", "data_snapshot_id", "configuration_snapshot_id", "software_version", "git_commit", "status", "checksum", "provenance"),
    "data_snapshots": ("snapshot_id", "project_id", "created_at", "datasets", "dataset_ids", "dataset_versions", "source_paths", "logical_paths", "checksums", "row_counts", "time_ranges", "crs", "units", "quality_status", "lineage_reference", "snapshot_mode", "provenance", "checksum"),
    "configuration_snapshots": ("snapshot_id", "project_id", "scenario_id", "workflow_id", "model_ids", "parameters", "parameter_provenance", "units", "runtime_options", "input_mapping", "data_requirements", "warnings", "created_at", "checksum"),
    "runs": ("run_id", "project_id", "project_version_id", "data_snapshot_id", "configuration_snapshot_id", "workflow_id", "run_name", "run_mode", "requested_at", "started_at", "finished_at", "status", "progress", "current_stage", "configuration_path", "configuration_checksum", "git_commit", "hydrolite_version", "python_version", "environment_id", "result_status", "error_summary", "legacy_unversioned", "warnings"),
    "tasks": ("task_id", "run_id", "stage_id", "task_type", "display_name", "command", "working_directory", "status", "attempt", "max_attempts", "timeout_seconds", "created_at", "started_at", "finished_at", "return_code", "process_id", "progress", "error_type", "error_message", "stdout_path", "stderr_path", "output_manifest", "retryable", "cancelled_by_user"),
    "artifacts": ("artifact_id", "run_id", "task_id", "project_id", "artifact_type", "display_name", "path", "relative_path", "media_type", "size", "checksum", "created_at", "source_stage", "quality_status", "preview_available", "downloadable", "lineage_dataset_id", "artifact_version", "supersedes_artifact_id", "frozen", "warnings"),
    "deliverables": ("deliverable_id", "project_id", "project_version_id", "run_ids", "artifact_ids", "report_ids", "created_at", "created_by", "review_status", "scientific_validation_level", "capabilities", "warnings", "limitations", "manifest_path", "manifest_hash", "package_hash", "supersedes", "provenance"),
    "reviews": ("review_id", "deliverable_id", "reviewer_name", "reviewer_role", "action", "comment", "created_at", "software_user_reference", "validation_snapshot", "warnings_snapshot"),
    "warning_acknowledgments": ("acknowledgment_id", "deliverable_id", "warning_code", "acknowledged_by", "acknowledged_at", "comment"),
    "audit_events": ("event_id", "timestamp", "project_id", "project_version_id", "deliverable_id", "actor", "action", "object_type", "object_id", "summary", "metadata"),
}
JSON_FIELDS = {
    "warnings", "command", "output_manifest", "scenario_ids", "provenance", "datasets",
    "dataset_ids", "dataset_versions", "source_paths", "logical_paths", "checksums",
    "row_counts", "time_ranges", "units", "model_ids", "parameters", "parameter_provenance",
    "runtime_options", "input_mapping", "data_requirements", "run_ids", "artifact_ids",
    "report_ids", "capabilities", "limitations", "validation_snapshot", "warnings_snapshot",
    "metadata",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path).expanduser().resolve() if db_path else get_runtime_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _raw_database_version(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    connection = sqlite3.connect(path)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not exists:
            return 0
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int((row or [0])[0] or 0)
    finally:
        connection.close()


def _backup_before_migration(path: Path, version: int) -> Path | None:
    if not path.exists() or path.stat().st_size == 0 or version >= SCHEMA_VERSION:
        return None
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}.schema-v{version or 'legacy'}.sqlite3.bak"
    if not backup.exists():
        source = sqlite3.connect(path)
        target = sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        backup.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return backup


def get_migration_backup_path(db_path: str | Path | None = None) -> Path | None:
    path = _path(db_path)
    backups = sorted((path.parent / "backups").glob(f"{path.stem}.schema-v*.sqlite3.bak"))
    return backups[-1] if backups else None


def _table_columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(db: sqlite3.Connection, table: str, name: str, declaration: str) -> None:
    if name not in _table_columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def _migrate_legacy_project_versions(db: sqlite3.Connection) -> None:
    columns = _table_columns(db, "project_versions")
    if "version_id" not in columns or "project_version_id" in columns:
        return
    db.execute("ALTER TABLE project_versions RENAME TO project_versions_v1")
    db.execute(
        """
        CREATE TABLE project_versions(
            project_version_id TEXT PRIMARY KEY, project_id TEXT, version_number INTEGER,
            parent_version_id TEXT, created_at TEXT, created_by TEXT, description TEXT,
            scenario_ids TEXT, data_snapshot_id TEXT, configuration_snapshot_id TEXT,
            software_version TEXT, git_commit TEXT, status TEXT, checksum TEXT, provenance TEXT
        )
        """
    )
    db.execute(
        """
        INSERT INTO project_versions(project_version_id, project_id, version_number, created_at, status, checksum, provenance)
        SELECT version_id, project_id, rowid, created_at, 'legacy_imported', checksum, metadata
        FROM project_versions_v1
        """
    )
    db.execute("DROP TABLE project_versions_v1")


@contextmanager
def _connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    try:
        connection = sqlite3.connect(_path(db_path), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        yield connection
        connection.commit()
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"Runtime database unavailable or corrupt: {exc}") from exc
    finally:
        if "connection" in locals():
            connection.close()


def initialize_runtime_database(db_path: str | Path | None = None) -> Path:
    path = _path(db_path)
    try:
        previous_version = _raw_database_version(path)
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"Runtime database unavailable or corrupt: {exc}") from exc
    _backup_before_migration(path, previous_version)
    with _connection(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS projects(project_id TEXT PRIMARY KEY, name TEXT, display_name TEXT, workspace_path TEXT UNIQUE, project_yaml TEXT, status TEXT, created_at TEXT, updated_at TEXT, last_opened_at TEXT, data_quality_status TEXT, workflow_readiness TEXT, checksum TEXT, archived INTEGER DEFAULT 0, warnings TEXT);
            CREATE TABLE IF NOT EXISTS project_versions(project_version_id TEXT PRIMARY KEY, project_id TEXT, version_number INTEGER, parent_version_id TEXT, created_at TEXT, created_by TEXT, description TEXT, scenario_ids TEXT, data_snapshot_id TEXT, configuration_snapshot_id TEXT, software_version TEXT, git_commit TEXT, status TEXT, checksum TEXT, provenance TEXT);
            CREATE TABLE IF NOT EXISTS data_snapshots(snapshot_id TEXT PRIMARY KEY, project_id TEXT, created_at TEXT, datasets TEXT, dataset_ids TEXT, dataset_versions TEXT, source_paths TEXT, logical_paths TEXT, checksums TEXT, row_counts TEXT, time_ranges TEXT, crs TEXT, units TEXT, quality_status TEXT, lineage_reference TEXT, snapshot_mode TEXT, provenance TEXT, checksum TEXT);
            CREATE TABLE IF NOT EXISTS configuration_snapshots(snapshot_id TEXT PRIMARY KEY, project_id TEXT, scenario_id TEXT, workflow_id TEXT, model_ids TEXT, parameters TEXT, parameter_provenance TEXT, units TEXT, runtime_options TEXT, input_mapping TEXT, data_requirements TEXT, warnings TEXT, created_at TEXT, checksum TEXT);
            CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, project_id TEXT, project_version_id TEXT, data_snapshot_id TEXT, configuration_snapshot_id TEXT, workflow_id TEXT, run_name TEXT, run_mode TEXT, requested_at TEXT, started_at TEXT, finished_at TEXT, status TEXT, progress REAL DEFAULT 0, current_stage TEXT, configuration_path TEXT, configuration_checksum TEXT, git_commit TEXT, hydrolite_version TEXT, python_version TEXT, environment_id TEXT, result_status TEXT, error_summary TEXT, legacy_unversioned INTEGER DEFAULT 1, warnings TEXT);
            CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, run_id TEXT, stage_id TEXT, task_type TEXT, display_name TEXT, command TEXT, working_directory TEXT, status TEXT, attempt INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 1, timeout_seconds INTEGER, created_at TEXT, started_at TEXT, finished_at TEXT, return_code INTEGER, process_id INTEGER, progress REAL DEFAULT 0, error_type TEXT, error_message TEXT, stdout_path TEXT, stderr_path TEXT, output_manifest TEXT, retryable INTEGER DEFAULT 0, cancelled_by_user INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS task_dependencies(task_id TEXT, depends_on_task_id TEXT, required INTEGER DEFAULT 1, PRIMARY KEY(task_id, depends_on_task_id));
            CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, project_id TEXT, artifact_type TEXT, display_name TEXT, path TEXT, relative_path TEXT, media_type TEXT, size INTEGER, checksum TEXT, created_at TEXT, source_stage TEXT, quality_status TEXT, preview_available INTEGER DEFAULT 0, downloadable INTEGER DEFAULT 1, lineage_dataset_id TEXT, artifact_version INTEGER DEFAULT 1, supersedes_artifact_id TEXT, frozen INTEGER DEFAULT 0, warnings TEXT);
            CREATE TABLE IF NOT EXISTS deliverables(deliverable_id TEXT PRIMARY KEY, project_id TEXT, project_version_id TEXT, run_ids TEXT, artifact_ids TEXT, report_ids TEXT, created_at TEXT, created_by TEXT, review_status TEXT, scientific_validation_level TEXT, capabilities TEXT, warnings TEXT, limitations TEXT, manifest_path TEXT, manifest_hash TEXT, package_hash TEXT, supersedes TEXT, provenance TEXT);
            CREATE TABLE IF NOT EXISTS reviews(review_id TEXT PRIMARY KEY, deliverable_id TEXT, reviewer_name TEXT, reviewer_role TEXT, action TEXT, comment TEXT, created_at TEXT, software_user_reference TEXT, validation_snapshot TEXT, warnings_snapshot TEXT);
            CREATE TABLE IF NOT EXISTS warning_acknowledgments(acknowledgment_id TEXT PRIMARY KEY, deliverable_id TEXT, warning_code TEXT, acknowledged_by TEXT, acknowledged_at TEXT, comment TEXT);
            CREATE TABLE IF NOT EXISTS audit_events(event_id TEXT PRIMARY KEY, timestamp TEXT, project_id TEXT, project_version_id TEXT, deliverable_id TEXT, actor TEXT, action TEXT, object_type TEXT, object_id TEXT, summary TEXT, metadata TEXT);
            CREATE TABLE IF NOT EXISTS logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, task_id TEXT, level TEXT, message TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS environments(environment_id TEXT PRIMARY KEY, created_at TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS connectors(connector_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS user_settings(setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS runtime_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, task_id TEXT, event_type TEXT, status TEXT, message TEXT, created_at TEXT);
            """
        )
        _migrate_legacy_project_versions(db)
        for name, declaration in (
            ("project_version_id", "TEXT"), ("data_snapshot_id", "TEXT"),
            ("configuration_snapshot_id", "TEXT"), ("legacy_unversioned", "INTEGER DEFAULT 1"),
        ):
            _ensure_column(db, "runs", name, declaration)
        for name, declaration in (
            ("artifact_version", "INTEGER DEFAULT 1"), ("supersedes_artifact_id", "TEXT"),
            ("frozen", "INTEGER DEFAULT 0"),
        ):
            _ensure_column(db, "artifacts", name, declaration)
        db.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)", (SCHEMA_VERSION, _now()))
    return path


def migrate_runtime_database(db_path: str | Path | None = None) -> int:
    initialize_runtime_database(db_path)
    return SCHEMA_VERSION


def get_database_version(db_path: str | Path | None = None) -> int:
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        row = db.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    return int(row["version"] or 0)


def _encode(field: str, value: Any) -> Any:
    if field in JSON_FIELDS and value is not None and not isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, default=str)
    return int(value) if isinstance(value, bool) else value


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for field in JSON_FIELDS:
        if field in result and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except json.JSONDecodeError:
                pass
    return result


def _create(table: str, values: dict[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    initialize_runtime_database(db_path)
    allowed = TABLE_COLUMNS[table]
    payload = {key: _encode(key, value) for key, value in values.items() if key in allowed}
    now = _now()
    if "created_at" in allowed:
        payload.setdefault("created_at", now)
    if "updated_at" in allowed:
        payload.setdefault("updated_at", now)
    columns = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    with _connection(db_path) as db:
        db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(payload.values()))
    return _get(table, payload[allowed[0]], db_path) or {}


def _update(table: str, record_id: str, values: dict[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    payload = {key: _encode(key, value) for key, value in values.items() if key in TABLE_COLUMNS[table][1:]}
    if "updated_at" in TABLE_COLUMNS[table]:
        payload["updated_at"] = _now()
    if payload:
        with _connection(db_path) as db:
            db.execute(f"UPDATE {table} SET {', '.join(f'{key}=?' for key in payload)} WHERE {TABLE_COLUMNS[table][0]}=?", (*payload.values(), record_id))
    return _get(table, record_id, db_path) or {}


def _get(table: str, record_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        row = db.execute(f"SELECT * FROM {table} WHERE {TABLE_COLUMNS[table][0]}=?", (record_id,)).fetchone()
    return _decode(row)


def _list(table: str, filters: dict[str, Any] | None = None, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    initialize_runtime_database(db_path)
    filters = filters or {}
    clauses, values = [], []
    for key, value in filters.items():
        if key in TABLE_COLUMNS[table]:
            clauses.append(f"{key}=?")
            values.append(value)
    query = f"SELECT * FROM {table}" + (f" WHERE {' AND '.join(clauses)}" if clauses else "") + " ORDER BY rowid DESC"
    with _connection(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return [_decode(row) or {} for row in rows]


def create_project_record(db_path=None, **values): return _create("projects", values, db_path)
def update_project_record(project_id, db_path=None, **values): return _update("projects", project_id, values, db_path)
def list_project_records(db_path=None, **filters): return _list("projects", filters, db_path)
def get_project_record(project_id, db_path=None): return _get("projects", project_id, db_path)
def delete_project_record(project_id, db_path=None):
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        db.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
def create_project_version_record(db_path=None, **values): return _create("project_versions", values, db_path)
def get_project_version_record(project_version_id, db_path=None): return _get("project_versions", project_version_id, db_path)
def list_project_version_records(db_path=None, **filters): return _list("project_versions", filters, db_path)
def create_data_snapshot_record(db_path=None, **values): return _create("data_snapshots", values, db_path)
def get_data_snapshot_record(snapshot_id, db_path=None): return _get("data_snapshots", snapshot_id, db_path)
def list_data_snapshot_records(db_path=None, **filters): return _list("data_snapshots", filters, db_path)
def create_configuration_snapshot_record(db_path=None, **values): return _create("configuration_snapshots", values, db_path)
def get_configuration_snapshot_record(snapshot_id, db_path=None): return _get("configuration_snapshots", snapshot_id, db_path)
def list_configuration_snapshot_records(db_path=None, **filters): return _list("configuration_snapshots", filters, db_path)
def create_run_record(db_path=None, **values): return _create("runs", values, db_path)
def update_run_record(run_id, db_path=None, **values): return _update("runs", run_id, values, db_path)
def list_run_records(db_path=None, **filters): return _list("runs", filters, db_path)
def get_run_record(run_id, db_path=None): return _get("runs", run_id, db_path)
def create_task_record(db_path=None, **values): return _create("tasks", values, db_path)
def update_task_record(task_id, db_path=None, **values): return _update("tasks", task_id, values, db_path)
def list_task_records(db_path=None, **filters): return _list("tasks", filters, db_path)
def get_task_record(task_id, db_path=None): return _get("tasks", task_id, db_path)
def create_artifact_record(db_path=None, **values): return _create("artifacts", values, db_path)
def update_artifact_record(artifact_id, db_path=None, **values): return _update("artifacts", artifact_id, values, db_path)
def list_artifact_records(db_path=None, **filters): return _list("artifacts", filters, db_path)
def get_artifact_record(artifact_id, db_path=None): return _get("artifacts", artifact_id, db_path)
def create_deliverable_record(db_path=None, **values): return _create("deliverables", values, db_path)
def update_deliverable_record(deliverable_id, db_path=None, **values): return _update("deliverables", deliverable_id, values, db_path)
def get_deliverable_record(deliverable_id, db_path=None): return _get("deliverables", deliverable_id, db_path)
def list_deliverable_records(db_path=None, **filters): return _list("deliverables", filters, db_path)
def create_review_record(db_path=None, **values): return _create("reviews", values, db_path)
def list_review_records(db_path=None, **filters): return _list("reviews", filters, db_path)
def create_warning_acknowledgment_record(db_path=None, **values): return _create("warning_acknowledgments", values, db_path)
def list_warning_acknowledgment_records(db_path=None, **filters): return _list("warning_acknowledgments", filters, db_path)
def create_audit_event_record(db_path=None, **values): return _create("audit_events", values, db_path)
def list_audit_event_records(db_path=None, **filters): return _list("audit_events", filters, db_path)


def create_log_record(run_id, task_id, level, message, db_path=None):
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        cursor = db.execute("INSERT INTO logs(run_id, task_id, level, message, created_at) VALUES(?,?,?,?,?)", (run_id, task_id, level, message, _now()))
    return cursor.lastrowid


def list_log_records(db_path=None, **filters):
    initialize_runtime_database(db_path)
    clauses, values = [], []
    for key in ("run_id", "task_id", "level"):
        if filters.get(key) is not None:
            clauses.append(f"{key}=?"); values.append(filters[key])
    with _connection(db_path) as db:
        rows = db.execute("SELECT * FROM logs" + (f" WHERE {' AND '.join(clauses)}" if clauses else "") + " ORDER BY log_id", values).fetchall()
    return [dict(row) for row in rows]


def create_environment_record(environment_id, payload, db_path=None):
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        db.execute("INSERT OR REPLACE INTO environments(environment_id, created_at, payload) VALUES(?,?,?)", (environment_id, _now(), json.dumps(payload, ensure_ascii=False, default=str)))
    return environment_id


def get_environment_record(environment_id, db_path=None):
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        row = db.execute("SELECT * FROM environments WHERE environment_id=?", (environment_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["payload"] = json.loads(result.get("payload") or "{}")
    except json.JSONDecodeError:
        pass
    return result


def create_runtime_event(run_id, task_id, event_type, status, message="", db_path=None):
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        db.execute("INSERT INTO runtime_events(run_id, task_id, event_type, status, message, created_at) VALUES(?,?,?,?,?,?)", (run_id, task_id, event_type, status, message, _now()))


def add_task_dependency(task_id: str, depends_on_task_id: str, required: bool = True, db_path=None) -> None:
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        db.execute("INSERT OR REPLACE INTO task_dependencies(task_id, depends_on_task_id, required) VALUES(?,?,?)", (task_id, depends_on_task_id, int(required)))


def list_task_dependencies(task_id: str | None = None, db_path=None) -> list[dict]:
    initialize_runtime_database(db_path)
    with _connection(db_path) as db:
        rows = db.execute(
            "SELECT * FROM task_dependencies" + (" WHERE task_id=?" if task_id else ""),
            (task_id,) if task_id else (),
        ).fetchall()
    return [dict(row) for row in rows]


def close_database(connection) -> None:
    if connection:
        connection.close()
