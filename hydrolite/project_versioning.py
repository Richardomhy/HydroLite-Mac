"""Immutable project, data, and configuration snapshots for delivery governance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import csv
import hashlib
from importlib import metadata
import json
import platform
import subprocess
import sys
import uuid

import yaml

from hydrolite.__version__ import __version__
from hydrolite.environment_capture import capture_optional_dependencies
from hydrolite.runtime_db import (
    create_audit_event_record,
    create_configuration_snapshot_record,
    create_data_snapshot_record,
    create_environment_record,
    create_project_record,
    create_project_version_record,
    get_project_record,
    get_project_version_record,
    list_project_records,
    list_project_version_records,
    update_run_record,
)
from hydrolite.runtime_paths import get_project_runtime_dir
from hydrolite.workspace import read_workspace_project_identity


PARAMETER_SOURCE_TYPES = {
    "default", "literature", "calibrated", "user_defined", "derived", "inherited", "unknown",
}
SNAPSHOT_MODES = {"metadata_only", "referenced", "portable"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False, timeout=10
    ).stdout.strip()


def _safe_logical_path(path: Path, workspace: Path) -> str:
    resolved = path.expanduser().resolve()
    for root, prefix in ((workspace.resolve(), "project"), (Path(__file__).resolve().parents[1], "workspace")):
        try:
            return f"{prefix}/{resolved.relative_to(root).as_posix()}"
        except ValueError:
            continue
    return f"external-reference/{resolved.name}"


def _resolve_input_path(value: str, workspace: Path) -> Path | None:
    candidate = Path(value).expanduser()
    roots = (workspace, Path(__file__).resolve().parents[1], workspace / "cases")
    if candidate.is_absolute():
        return candidate.resolve() if candidate.exists() else None
    for root in roots:
        path = (root / candidate).resolve()
        if path.exists() and path.is_file():
            return path
    return None


def _iter_path_values(payload: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, str) and (
                str(key).endswith(("_csv", "_file", "_path"))
                or str(key) in {"basin_boundary", "inp_file", "source_flow_csv"}
            ):
                yield name, value
            else:
                yield from _iter_path_values(value, name)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _iter_path_values(value, f"{prefix}[{index}]")


def _table_metadata(path: Path) -> tuple[int | None, dict[str, str]]:
    if path.suffix.lower() != ".csv":
        return None, {}
    count = 0
    first: dict[str, str] | None = None
    last: dict[str, str] | None = None
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                first = first or row
                last = row
                count += 1
    except (OSError, UnicodeError, csv.Error):
        return None, {}
    time_key = next((key for key in (first or {}) if key.casefold() in {"datetime", "timestamp", "time", "date"}), None)
    time_range = {"start": str((first or {}).get(time_key, "")), "end": str((last or {}).get(time_key, ""))} if time_key else {}
    return count, time_range


def _flatten_parameters(payload: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "parameter_provenance":
                continue
            name = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_parameters(value, name))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            rows.extend(_flatten_parameters(value, f"{prefix}[{index}]"))
    elif isinstance(payload, (str, int, float, bool)) or payload is None:
        rows.append({
            "parameter_name": prefix,
            "value": payload,
            "unit": "unknown",
            "source_type": "unknown",
            "source_reference": "configuration snapshot",
            "modified_by": "unknown",
            "modified_at": "unknown",
            "confidence": "unknown",
            "notes": "Source not declared in the working configuration.",
        })
    return rows


@dataclass(frozen=True, slots=True)
class ProjectVersion:
    project_version_id: str
    project_id: str
    version_number: int
    parent_version_id: str | None
    created_at: str
    created_by: str
    description: str
    scenario_ids: tuple[str, ...]
    data_snapshot_id: str
    configuration_snapshot_id: str
    software_version: str
    git_commit: str
    status: str
    checksum: str
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_project(project: str | Path) -> dict[str, Any]:
    reference = str(project)
    record = get_project_record(reference)
    if record:
        return record
    path = Path(reference).expanduser()
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Project not found: {reference}")
    root = path.resolve()
    existing = list_project_records(workspace_path=str(root))
    if existing:
        return existing[0]
    config_path = root / "project.yaml"
    if not config_path.exists():
        raise ValueError(f"project.yaml is missing: {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    identity = read_workspace_project_identity(config, root.name)
    project_id = identity["project_id"] or f"prj_{uuid.uuid4().hex[:12]}"
    if get_project_record(project_id):
        project_id = f"{project_id}_{uuid.uuid4().hex[:6]}"
    created = create_project_record(
        project_id=project_id,
        name=identity["name"],
        display_name=identity["display_name"],
        workspace_path=str(root),
        project_yaml=str(config_path),
        status="ready_with_warnings",
        data_quality_status="unknown",
        workflow_readiness="partial",
        checksum=_hash_file(config_path),
        archived=False,
        warnings=["workspace_manifest.json missing"] if not (root / "workspace_manifest.json").exists() else [],
    )
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=project_id,
        project_version_id="", deliverable_id="", actor="local_user", action="project_created",
        object_type="project", object_id=project_id, summary="Project registered for delivery governance.", metadata={},
    )
    return created


def _snapshot_dir(project_id: str) -> Path:
    path = get_project_runtime_dir(project_id) / "delivery" / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_data_snapshot(project: str | Path, *, snapshot_mode: str = "referenced") -> dict[str, Any]:
    if snapshot_mode not in SNAPSHOT_MODES:
        raise ValueError(f"Unsupported snapshot mode: {snapshot_mode}")
    record = resolve_project(project)
    workspace = Path(record["workspace_path"])
    config_files = [workspace / "project.yaml", *sorted((workspace / "cases").glob("*.y*ml"))]
    discovered: dict[str, Path] = {}
    manifest_path = workspace / "workspace_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for item in manifest.get("datasets", []):
        if not isinstance(item, dict):
            continue
        value = item.get("processed_path") or item.get("logical_path") or item.get("path")
        path = _resolve_input_path(str(value), workspace) if value else None
        if path:
            discovered[str(item.get("dataset_id") or item.get("dataset_type") or path.name)] = path
    for config_file in config_files:
        if not config_file.exists():
            continue
        payload = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        for key, value in _iter_path_values(payload):
            path = _resolve_input_path(value, workspace)
            if path:
                discovered.setdefault(key, path)

    datasets: list[dict[str, Any]] = []
    for dataset_id, path in sorted(discovered.items()):
        row_count, time_range = _table_metadata(path)
        datasets.append({
            "dataset_id": dataset_id,
            "dataset_version": "content-addressed",
            "source_path": _safe_logical_path(path, workspace),
            "logical_path": _safe_logical_path(path, workspace),
            "checksum": _hash_file(path),
            "row_count": row_count,
            "time_range": time_range,
            "crs": "unknown",
            "units": "declared_in_source_or_unknown",
        })
    created_at = _now()
    snapshot_id = f"data_{uuid.uuid4().hex[:12]}"
    body = {
        "snapshot_id": snapshot_id,
        "project_id": record["project_id"],
        "created_at": created_at,
        "datasets": datasets,
        "snapshot_mode": snapshot_mode,
        "quality_status": "ready_with_warnings" if not datasets else "referenced",
        "lineage_reference": "workspace_manifest.json" if manifest_path.exists() else "case configuration discovery",
        "provenance": {"immutable_source_read": True, "raw_data_modified": False},
    }
    body["checksum"] = _canonical_hash(body)
    stored = create_data_snapshot_record(
        snapshot_id=snapshot_id,
        project_id=record["project_id"],
        created_at=created_at,
        datasets=datasets,
        dataset_ids=[row["dataset_id"] for row in datasets],
        dataset_versions={row["dataset_id"]: row["dataset_version"] for row in datasets},
        source_paths={row["dataset_id"]: row["source_path"] for row in datasets},
        logical_paths={row["dataset_id"]: row["logical_path"] for row in datasets},
        checksums={row["dataset_id"]: row["checksum"] for row in datasets},
        row_counts={row["dataset_id"]: row["row_count"] for row in datasets},
        time_ranges={row["dataset_id"]: row["time_range"] for row in datasets},
        crs="mixed_or_unknown",
        units={row["dataset_id"]: row["units"] for row in datasets},
        quality_status=body["quality_status"],
        lineage_reference=body["lineage_reference"],
        snapshot_mode=snapshot_mode,
        provenance=body["provenance"],
        checksum=body["checksum"],
    )
    (_snapshot_dir(record["project_id"]) / "data_snapshot_manifest.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=created_at, project_id=record["project_id"],
        project_version_id="", deliverable_id="", actor="local_user", action="data_snapshot_created",
        object_type="data_snapshot", object_id=snapshot_id, summary="Immutable referenced data snapshot created.", metadata={"snapshot_mode": snapshot_mode},
    )
    return stored


def create_configuration_snapshot(project: str | Path, *, scenario_id: str = "", workflow_id: str = "") -> dict[str, Any]:
    record = resolve_project(project)
    workspace = Path(record["workspace_path"])
    project_config = yaml.safe_load((workspace / "project.yaml").read_text(encoding="utf-8")) or {}
    case_files = sorted((workspace / "cases").glob("*.y*ml"))
    selected = next((path for path in case_files if path.stem == scenario_id), case_files[0] if case_files else None)
    case_config = yaml.safe_load(selected.read_text(encoding="utf-8")) or {} if selected else {}
    parameters = {"project": project_config, "scenario": case_config}
    explicit = case_config.get("parameter_provenance", {}) if isinstance(case_config, dict) else {}
    provenance_rows = _flatten_parameters(parameters)
    for row in provenance_rows:
        override = explicit.get(row["parameter_name"], {}) if isinstance(explicit, dict) else {}
        if isinstance(override, dict):
            row.update({key: value for key, value in override.items() if key in row})
        if row["source_type"] not in PARAMETER_SOURCE_TYPES:
            raise ValueError(f"Invalid parameter source_type: {row['source_type']}")
    created_at = _now()
    snapshot_id = f"cfg_{uuid.uuid4().hex[:12]}"
    body = {
        "snapshot_id": snapshot_id,
        "project_id": record["project_id"],
        "scenario_id": scenario_id or (selected.stem if selected else ""),
        "workflow_id": workflow_id or "unspecified",
        "model_ids": [],
        "parameters": parameters,
        "parameter_provenance": provenance_rows,
        "units": {},
        "runtime_options": {},
        "input_mapping": dict(_iter_path_values(case_config)),
        "data_requirements": [],
        "warnings": ["Unknown parameter provenance remains"] if any(row["source_type"] == "unknown" for row in provenance_rows) else [],
        "created_at": created_at,
    }
    body["checksum"] = _canonical_hash(body)
    stored = create_configuration_snapshot_record(**body)
    (_snapshot_dir(record["project_id"]) / "configuration_snapshot.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=created_at, project_id=record["project_id"],
        project_version_id="", deliverable_id="", actor="local_user", action="config_snapshot_created",
        object_type="configuration_snapshot", object_id=snapshot_id, summary="Immutable configuration snapshot created.", metadata={},
    )
    return stored


def create_project_version(
    project: str | Path, *, created_by: str = "local_user", description: str = "",
    scenario_ids: Iterable[str] = (), snapshot_mode: str = "referenced", status: str = "frozen",
) -> dict[str, Any]:
    record = resolve_project(project)
    previous = sorted(list_project_version_records(project_id=record["project_id"]), key=lambda row: int(row.get("version_number") or 0))
    version_number = int(previous[-1]["version_number"] or 0) + 1 if previous else 1
    parent_id = previous[-1]["project_version_id"] if previous else None
    data = create_data_snapshot(record["project_id"], snapshot_mode=snapshot_mode)
    config = create_configuration_snapshot(record["project_id"], scenario_id=next(iter(scenario_ids), ""))
    created_at = _now()
    version_id = f"pv_{uuid.uuid4().hex[:12]}"
    body = ProjectVersion(
        project_version_id=version_id,
        project_id=record["project_id"],
        version_number=version_number,
        parent_version_id=parent_id,
        created_at=created_at,
        created_by=created_by,
        description=description,
        scenario_ids=tuple(scenario_ids),
        data_snapshot_id=data["snapshot_id"],
        configuration_snapshot_id=config["snapshot_id"],
        software_version=__version__,
        git_commit=_git_commit(),
        status=status,
        checksum="",
        provenance={"working_copy_independent": True, "snapshot_mode": snapshot_mode},
    ).as_dict()
    body["checksum"] = _canonical_hash({key: value for key, value in body.items() if key != "checksum"})
    stored = create_project_version_record(**body)
    (_snapshot_dir(record["project_id"]) / "project_version_manifest.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=created_at, project_id=record["project_id"],
        project_version_id=version_id, deliverable_id="", actor=created_by, action="project_version_created",
        object_type="project_version", object_id=version_id, summary=f"Project version {version_number} created.", metadata={"parent_version_id": parent_id},
    )
    return stored


def list_project_versions(project: str | Path) -> list[dict[str, Any]]:
    record = resolve_project(project)
    return sorted(list_project_version_records(project_id=record["project_id"]), key=lambda row: int(row.get("version_number") or 0))


def show_project_version(project_version_id: str) -> dict[str, Any]:
    record = get_project_version_record(project_version_id)
    if not record:
        raise KeyError(f"Unknown project version: {project_version_id}")
    return record


def compare_project_versions(left_id: str, right_id: str) -> dict[str, Any]:
    left, right = show_project_version(left_id), show_project_version(right_id)
    fields = ("data_snapshot_id", "configuration_snapshot_id", "scenario_ids", "checksum")
    return {
        "left": left_id,
        "right": right_id,
        "changes": {field: {"left": left.get(field), "right": right.get(field)} for field in fields if left.get(field) != right.get(field)},
    }


def capture_delivery_environment(project_version_id: str) -> dict[str, Any]:
    version = show_project_version(project_version_id)
    environment_id = f"env_{uuid.uuid4().hex[:12]}"
    critical_packages = {}
    for name in ("streamlit", "pandas", "numpy", "matplotlib", "openpyxl", "pyyaml", "scipy"):
        try: critical_packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError: critical_packages[name] = "not_installed"
    payload = {
        "environment_id": environment_id,
        "captured_at": _now(),
        "hydrolite_version": __version__,
        "git_commit": _git_commit(),
        "python_version": sys.version.split()[0],
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "critical_packages": critical_packages,
        "optional_backend_status": capture_optional_dependencies(),
        "paths_sanitized": True,
        "credentials_recorded": False,
        "project_version_id": project_version_id,
    }
    create_environment_record(environment_id, payload)
    return payload


def link_run_to_project_version(run_id: str, project_version_id: str) -> dict[str, Any]:
    version = show_project_version(project_version_id)
    environment = capture_delivery_environment(project_version_id)
    result = update_run_record(
        run_id,
        project_version_id=project_version_id,
        data_snapshot_id=version["data_snapshot_id"],
        configuration_snapshot_id=version["configuration_snapshot_id"],
        environment_id=environment["environment_id"],
        legacy_unversioned=False,
    )
    if not result:
        raise KeyError(f"Unknown run: {run_id}")
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=version["project_id"],
        project_version_id=project_version_id, deliverable_id="", actor="local_user", action="run_linked",
        object_type="run", object_id=run_id, summary="Run linked to immutable project snapshots.", metadata={"environment_id": environment["environment_id"]},
    )
    return result
