from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterator

from hydrolite.runtime_paths import get_runtime_db_path


SCHEMA_VERSION = 1
TABLE_COLUMNS = {
    "projects": ("project_id", "name", "display_name", "workspace_path", "project_yaml", "status", "created_at", "updated_at", "last_opened_at", "data_quality_status", "workflow_readiness", "checksum", "archived", "warnings"),
    "runs": ("run_id", "project_id", "workflow_id", "run_name", "run_mode", "requested_at", "started_at", "finished_at", "status", "progress", "current_stage", "configuration_path", "configuration_checksum", "git_commit", "hydrolite_version", "python_version", "environment_id", "result_status", "error_summary", "warnings"),
    "tasks": ("task_id", "run_id", "stage_id", "task_type", "display_name", "command", "working_directory", "status", "attempt", "max_attempts", "timeout_seconds", "created_at", "started_at", "finished_at", "return_code", "process_id", "progress", "error_type", "error_message", "stdout_path", "stderr_path", "output_manifest", "retryable", "cancelled_by_user"),
    "artifacts": ("artifact_id", "run_id", "task_id", "project_id", "artifact_type", "display_name", "path", "relative_path", "media_type", "size", "checksum", "created_at", "source_stage", "quality_status", "preview_available", "downloadable", "lineage_dataset_id", "warnings"),
}
JSON_FIELDS = {"warnings", "command", "output_manifest"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path).expanduser().resolve() if db_path else get_runtime_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


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
    with _connection(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS projects(project_id TEXT PRIMARY KEY, name TEXT, display_name TEXT, workspace_path TEXT UNIQUE, project_yaml TEXT, status TEXT, created_at TEXT, updated_at TEXT, last_opened_at TEXT, data_quality_status TEXT, workflow_readiness TEXT, checksum TEXT, archived INTEGER DEFAULT 0, warnings TEXT);
            CREATE TABLE IF NOT EXISTS project_versions(version_id TEXT PRIMARY KEY, project_id TEXT, checksum TEXT, created_at TEXT, metadata TEXT);
            CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, project_id TEXT, workflow_id TEXT, run_name TEXT, run_mode TEXT, requested_at TEXT, started_at TEXT, finished_at TEXT, status TEXT, progress REAL DEFAULT 0, current_stage TEXT, configuration_path TEXT, configuration_checksum TEXT, git_commit TEXT, hydrolite_version TEXT, python_version TEXT, environment_id TEXT, result_status TEXT, error_summary TEXT, warnings TEXT);
            CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, run_id TEXT, stage_id TEXT, task_type TEXT, display_name TEXT, command TEXT, working_directory TEXT, status TEXT, attempt INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 1, timeout_seconds INTEGER, created_at TEXT, started_at TEXT, finished_at TEXT, return_code INTEGER, process_id INTEGER, progress REAL DEFAULT 0, error_type TEXT, error_message TEXT, stdout_path TEXT, stderr_path TEXT, output_manifest TEXT, retryable INTEGER DEFAULT 0, cancelled_by_user INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS task_dependencies(task_id TEXT, depends_on_task_id TEXT, required INTEGER DEFAULT 1, PRIMARY KEY(task_id, depends_on_task_id));
            CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, project_id TEXT, artifact_type TEXT, display_name TEXT, path TEXT, relative_path TEXT, media_type TEXT, size INTEGER, checksum TEXT, created_at TEXT, source_stage TEXT, quality_status TEXT, preview_available INTEGER DEFAULT 0, downloadable INTEGER DEFAULT 1, lineage_dataset_id TEXT, warnings TEXT);
            CREATE TABLE IF NOT EXISTS logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, task_id TEXT, level TEXT, message TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS environments(environment_id TEXT PRIMARY KEY, created_at TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS connectors(connector_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS user_settings(setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS runtime_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, task_id TEXT, event_type TEXT, status TEXT, message TEXT, created_at TEXT);
            """
        )
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
