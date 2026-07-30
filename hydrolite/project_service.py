from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import uuid
import zipfile

import yaml

from hydrolite.runtime_db import (
    create_project_record,
    delete_project_record,
    get_project_record,
    list_project_records,
    update_project_record,
)
from hydrolite.runtime_paths import get_project_runtime_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and not any(part in {"raw", "uploads", "external", "cache", "outputs", "logs"} for part in candidate.relative_to(path).parts):
            digest.update(candidate.relative_to(path).as_posix().encode())
            digest.update(candidate.read_bytes())
    return digest.hexdigest()


def _load_project_metadata(root: Path) -> dict:
    project_yaml = root / "project.yaml"
    manifest_path = root / "workspace_manifest.json"
    config = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) if project_yaml.exists() else {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return {"config": config or {}, "manifest": manifest or {}, "project_yaml": project_yaml, "manifest_path": manifest_path}


def register_workspace_as_project(workspace_dir: str | Path) -> dict:
    root = Path(workspace_dir).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Workspace not found: {root}")
    existing = list_project_records(workspace_path=str(root))
    if existing:
        return existing[0]
    metadata = _load_project_metadata(root)
    if not metadata["project_yaml"].exists() or not metadata["manifest_path"].exists():
        raise ValueError("Workspace requires project.yaml and workspace_manifest.json")
    config, manifest = metadata["config"], metadata["manifest"]
    project_id = f"prj_{uuid.uuid4().hex[:12]}"
    datasets = manifest.get("datasets", [])
    qualities = {row.get("quality_status") for row in datasets if row.get("quality_status")}
    data_quality = "ready" if datasets and qualities <= {"ready", "ready_with_warnings"} else ("needs_data" if not datasets else "needs_repair")
    record = create_project_record(
        project_id=project_id,
        name=str(config.get("project_name") or root.name),
        display_name=str(config.get("display_name") or config.get("project_name") or root.name),
        workspace_path=str(root),
        project_yaml=str(metadata["project_yaml"]),
        status="ready" if data_quality == "ready" else data_quality,
        last_opened_at=_now(),
        data_quality_status=data_quality,
        workflow_readiness="partial",
        checksum=_checksum(root),
        archived=False,
        warnings=[],
    )
    runtime_project = get_project_runtime_dir(project_id)
    runtime_project.mkdir(parents=True, exist_ok=True)
    (runtime_project / "project_record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def import_existing_project(project_dir: str | Path) -> dict:
    return register_workspace_as_project(project_dir)


def create_project_from_data_center(workspace_dir: str | Path, project_name: str) -> dict:
    root = Path(workspace_dir).expanduser().resolve()
    project_yaml = root / "project.yaml"
    config = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    config["project_name"] = project_name
    project_yaml.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return register_workspace_as_project(root)


def open_project(project_id: str) -> dict:
    record = get_project_record(project_id)
    if not record:
        raise KeyError(f"Unknown project_id: {project_id}")
    return update_project_record(project_id, last_opened_at=_now())


def validate_project_service_record(project_id: str) -> dict:
    record = get_project_record(project_id)
    errors = []
    if not record:
        errors.append("project record is missing")
        return {"status": "failed", "errors": errors}
    root = Path(record["workspace_path"])
    if not root.exists(): errors.append("workspace path does not exist")
    if not (root / "project.yaml").exists(): errors.append("project.yaml is missing")
    if not (root / "workspace_manifest.json").exists(): errors.append("workspace_manifest.json is missing")
    return {"status": "passed" if not errors else "failed", "errors": errors, "project_id": project_id}


def update_project_readiness(project_id: str) -> dict:
    validation = validate_project_service_record(project_id)
    readiness = "ready" if validation["status"] == "passed" else "blocked"
    return update_project_record(project_id, workflow_readiness=readiness, status="ready" if readiness == "ready" else "needs_repair", warnings=validation["errors"])


def archive_project(project_id: str) -> dict:
    return update_project_record(project_id, archived=True, status="archived")


def unarchive_project(project_id: str) -> dict:
    return update_project_record(project_id, archived=False, status="ready")


def delete_project_registration(project_id: str, confirm: bool = False) -> dict:
    if not confirm:
        raise ValueError("Confirm removal of the project registration; workspace files are never deleted")
    record = get_project_record(project_id)
    if not record:
        raise KeyError(f"Unknown project_id: {project_id}")
    delete_project_record(project_id)
    return {"project_id": project_id, "status": "registration_deleted", "workspace_deleted": False}


def duplicate_project(project_id: str, new_name: str) -> dict:
    source = open_project(project_id)
    target = Path(source["workspace_path"]).parent / f"{new_name}_{uuid.uuid4().hex[:6]}"
    shutil.copytree(source["workspace_path"], target, ignore=shutil.ignore_patterns("raw", "uploads", "external", "outputs", "logs", "cache"))
    config_path = target / "project.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config["project_name"] = new_name
    config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return register_workspace_as_project(target)


def export_project_metadata(project_id: str, output_path: str | Path) -> Path:
    record = open_project(project_id)
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    safe = {key: value for key, value in record.items() if key != "workspace_path"}
    safe["workspace_name"] = Path(record["workspace_path"]).name
    target.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def create_project_snapshot(project_id: str, output_path: str | Path) -> Path:
    record = open_project(project_id)
    root = Path(record["workspace_path"])
    target = Path(output_path)
    if target.suffix.lower() != ".zip":
        target = target / f"{project_id}_snapshot.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("project.yaml", "workspace_manifest.json"):
            path = root / name
            if path.exists(): archive.write(path, name)
        archive.writestr("project_record.json", json.dumps({**record, "workspace_path": root.name}, indent=2, ensure_ascii=False))
    return target


def list_recent_projects() -> list[dict]:
    return list_project_records()[:10]


def search_projects(query: str) -> list[dict]:
    needle = query.casefold()
    return [row for row in list_project_records() if needle in f"{row.get('name','')} {row.get('display_name','')}".casefold()]


def write_project_summary(project_id: str, output_dir: str | Path) -> Path:
    record = open_project(project_id)
    path = Path(output_dir) / "project_operations_summary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Project Operations Summary\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in record.items() if key != "workspace_path") + "\n", encoding="utf-8")
    return path
