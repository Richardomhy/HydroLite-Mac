from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import shutil
import zipfile
from typing import Any

import yaml


WORKSPACE_DIRS = (
    "raw", "uploads", "external", "staging", "standardized", "vector", "raster",
    "timeseries", "tables", "models", "mappings", "quality", "lineage", "derived",
    "outputs", "reports", "logs", "cache",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def calculate_file_checksum(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_workspace(workspace_dir: str | Path, project_name: str) -> dict[str, Any]:
    root = Path(workspace_dir).expanduser().resolve()
    if "data_raw" in root.parts:
        raise ValueError("Workspace cannot be created inside data_raw.")
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Workspace is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for name in WORKSPACE_DIRS:
        (root / name).mkdir(exist_ok=True)
    project_id = re.sub(r"[^a-z0-9_-]+", "_", project_name.lower()).strip("_") or "hydrolite_project"
    project = {
        "project": {"name": project_name, "id": project_id, "created_at": _now()},
        "workspace": {"root": ".", "raw_read_only": True, "synthetic_demo": False},
    }
    (root / "project.yaml").write_text(yaml.safe_dump(project, sort_keys=False, allow_unicode=True), encoding="utf-8")
    manifest = {"schema_version": 1, "project_id": project_id, "project_name": project_name, "created_at": _now(), "datasets": [], "snapshots": []}
    write_workspace_manifest(root, manifest)
    return inspect_workspace(root)


def inspect_workspace(workspace_dir: str | Path) -> dict[str, Any]:
    root = Path(workspace_dir).expanduser().resolve()
    return {
        "status": "ready" if root.is_dir() and (root / "workspace_manifest.json").is_file() else "invalid",
        "workspace_dir": str(root),
        "project_yaml": str(root / "project.yaml"),
        "manifest": str(root / "workspace_manifest.json"),
        "directories": {name: (root / name).is_dir() for name in WORKSPACE_DIRS},
        "dataset_count": len(read_workspace_manifest(root).get("datasets", [])) if (root / "workspace_manifest.json").is_file() else 0,
    }


def validate_workspace(workspace_dir: str | Path) -> dict[str, Any]:
    inspection = inspect_workspace(workspace_dir)
    missing = [name for name, exists in inspection["directories"].items() if not exists]
    errors = ([] if inspection["status"] == "ready" else ["workspace_manifest.json is missing"]) + [f"Missing directory: {name}" for name in missing]
    return {**inspection, "status": "passed" if not errors else "failed", "errors": errors}


def lock_workspace_raw_files(workspace_dir: str | Path) -> list[str]:
    raw = Path(workspace_dir).expanduser().resolve() / "raw"
    locked: list[str] = []
    for path in raw.rglob("*"):
        if path.is_file():
            path.chmod(path.stat().st_mode & ~0o222)
            locked.append(str(path))
    return locked


def list_workspace_datasets(workspace_dir: str | Path) -> list[dict[str, Any]]:
    return list(read_workspace_manifest(workspace_dir).get("datasets", []))


def write_workspace_manifest(workspace_dir: str | Path, manifest: dict[str, Any]) -> Path:
    path = Path(workspace_dir).expanduser().resolve() / "workspace_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(manifest)
    safe["updated_at"] = _now()
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_workspace_manifest(workspace_dir: str | Path) -> dict[str, Any]:
    path = Path(workspace_dir).expanduser().resolve() / "workspace_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def create_workspace_snapshot(workspace_dir: str | Path, output_path: str | Path) -> Path:
    root = Path(workspace_dir).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file() and "cache" not in path.relative_to(root).parts:
                archive.write(path, path.relative_to(root))
    return target


def restore_workspace_snapshot(snapshot_path: str | Path, workspace_dir: str | Path, execute: bool = False) -> dict[str, Any]:
    snapshot = Path(snapshot_path).expanduser().resolve()
    target = Path(workspace_dir).expanduser().resolve()
    result = {"status": "dry_run", "snapshot": str(snapshot), "workspace_dir": str(target), "execute": execute}
    if not execute:
        return result
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Restore target is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snapshot) as archive:
        for item in archive.infolist():
            resolved = (target / item.filename).resolve()
            if target not in resolved.parents and resolved != target:
                raise ValueError(f"Unsafe snapshot member: {item.filename}")
        archive.extractall(target)
    result["status"] = "restored"
    return result
