"""Machine-readable and human-readable manifests for reviewed deliverables."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import shutil

from hydrolite.__version__ import __version__
from hydrolite.integrity_verification import hash_manifest
from hydrolite.runtime_db import (
    get_artifact_record,
    get_configuration_snapshot_record,
    get_data_snapshot_record,
    get_deliverable_record,
    get_environment_record,
    get_project_record,
    get_project_version_record,
    get_run_record,
    list_review_records,
    list_task_records,
    list_warning_acknowledgment_records,
    update_deliverable_record,
)
from hydrolite.runtime_paths import get_project_runtime_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_manifest_paths(value: Any, project_root: str | Path | None = None) -> Any:
    root = Path(project_root).resolve() if project_root else None
    if isinstance(value, dict):
        return {key: sanitize_manifest_paths(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_manifest_paths(item, root) for item in value]
    if isinstance(value, tuple):
        return [sanitize_manifest_paths(item, root) for item in value]
    if not isinstance(value, str) or value.startswith(("http://", "https://", "gs://")):
        return value
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return value.replace("\\", "/")
    resolved = candidate.resolve()
    if root:
        try:
            return f"project/{resolved.relative_to(root).as_posix()}"
        except ValueError:
            pass
    return f"external-reference/{resolved.name}"


def build_deliverable_manifest(deliverable_id: str) -> dict[str, Any]:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(f"Unknown deliverable: {deliverable_id}")
    version = get_project_version_record(deliverable["project_version_id"])
    if not version:
        raise ValueError("Deliverable project version is missing")
    project = get_project_record(deliverable["project_id"])
    project_root = Path(project["workspace_path"]) if project else None
    data_snapshot = get_data_snapshot_record(version["data_snapshot_id"])
    config_snapshot = get_configuration_snapshot_record(version["configuration_snapshot_id"])
    runs = [get_run_record(run_id) for run_id in deliverable.get("run_ids", [])]
    runs = [row for row in runs if row]
    tasks = [task for run in runs for task in list_task_records(run_id=run["run_id"])]
    artifacts = [get_artifact_record(artifact_id) for artifact_id in deliverable.get("artifact_ids", [])]
    artifacts = [row for row in artifacts if row]
    reports = [get_artifact_record(artifact_id) for artifact_id in deliverable.get("report_ids", [])]
    reports = [row for row in reports if row]
    environments = [get_environment_record(run.get("environment_id")) for run in runs if run.get("environment_id")]
    payload = {
        "manifest_schema_version": 1,
        "project": project,
        "project_version": version,
        "scenarios": version.get("scenario_ids", []),
        "data_snapshot": data_snapshot,
        "configuration_snapshot": config_snapshot,
        "runs": runs,
        "tasks": tasks,
        "models": (config_snapshot or {}).get("model_ids", []),
        "capabilities": deliverable.get("capabilities", []),
        "artifacts": artifacts,
        "reports": reports,
        "environment": environments,
        "validation": {
            "scientific_validation_level": deliverable.get("scientific_validation_level"),
            "real_data_validation": deliverable.get("scientific_validation_level") in {"real_data_tested", "independently_validated", "production_ready"},
            "experimental": deliverable.get("scientific_validation_level") == "synthetic_demo",
            "xai_stability": "unstable" if "XAI_IMPORTANCE_UNSTABLE" in deliverable.get("warnings", []) else "not_assessed",
            "complex_model_value_added": "not_demonstrated" if "flood_susceptibility" in deliverable.get("capabilities", []) else "not_assessed",
        },
        "delivery_labels": ["EXPERIMENTAL"] if deliverable.get("scientific_validation_level") == "synthetic_demo" else [],
        "warnings": deliverable.get("warnings", []),
        "warning_acknowledgments": list_warning_acknowledgment_records(deliverable_id=deliverable_id),
        "limitations": deliverable.get("limitations", []),
        "review_status": deliverable.get("review_status"),
        "review_history": list_review_records(deliverable_id=deliverable_id),
        "checksums": {
            "project_version": version.get("checksum"),
            "data_snapshot": (data_snapshot or {}).get("checksum"),
            "configuration_snapshot": (config_snapshot or {}).get("checksum"),
            "artifacts": {row["artifact_id"]: row.get("checksum") for row in artifacts},
            "reports": {row["artifact_id"]: row.get("checksum") for row in reports},
        },
        "software_version": __version__,
        "git_commit": version.get("git_commit"),
        "generated_time": _now(),
        "delivery_status_notice": "Delivery approval is separate from scientific validation and production readiness.",
    }
    safe = sanitize_manifest_paths(payload, project_root)
    safe["manifest_hash"] = hash_manifest(safe)
    return safe


def write_deliverable_manifest(deliverable_id: str, output_dir: str | Path | None = None, *, force: bool = False) -> dict[str, Path]:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(deliverable_id)
    existing_manifest = Path(str(deliverable.get("manifest_path") or ""))
    existing_summary = existing_manifest.parent / "README_交付说明.md" if existing_manifest.name else Path()
    if deliverable.get("review_status") == "approved_for_delivery" and existing_manifest.is_file() and not force:
        if output_dir:
            output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
            target_manifest, target_summary = output / "deliverable_manifest.json", output / "README_交付说明.md"
            shutil.copy2(existing_manifest, target_manifest)
            if existing_summary.is_file(): shutil.copy2(existing_summary, target_summary)
            return {"manifest": target_manifest, "summary": target_summary}
        return {"manifest": existing_manifest, "summary": existing_summary}
    output = Path(output_dir) if output_dir else get_project_runtime_dir(deliverable["project_id"]) / "delivery" / deliverable_id
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_deliverable_manifest(deliverable_id)
    json_path = output / "deliverable_manifest.json"
    summary_path = output / "README_交付说明.md"
    json_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary_path.write_text(
        "# HydroLite 交付说明\n\n"
        f"- Deliverable: `{deliverable_id}`\n"
        f"- Project Version: `{deliverable['project_version_id']}`\n"
        f"- Delivery Review: `{deliverable['review_status']}`\n"
        f"- Scientific Validation: `{deliverable['scientific_validation_level']}`\n"
        f"- Manifest SHA-256: `{manifest['manifest_hash']}`\n\n"
        "交付审核通过不等于科学验证通过，也不等于模型已达到生产级。\n",
        encoding="utf-8",
    )
    update_deliverable_record(deliverable_id, manifest_path=str(json_path), manifest_hash=manifest["manifest_hash"])
    return {"manifest": json_path, "summary": summary_path}


def write_report_delivery_metadata(report_artifact_id: str, deliverable_id: str, *, report_version: int = 1) -> Path:
    deliverable = get_deliverable_record(deliverable_id)
    report = get_artifact_record(report_artifact_id)
    if not deliverable or not report:
        raise KeyError("Deliverable or report artifact is missing")
    version = get_project_version_record(deliverable["project_version_id"]) or {}
    metadata = {
        "project": deliverable["project_id"],
        "project_version": version.get("version_number"),
        "scenario": version.get("scenario_ids", []),
        "run_id": report.get("run_id"),
        "report_version": report_version,
        "hydrolite_version": __version__,
        "git_commit": version.get("git_commit"),
        "generated_at": _now(),
        "review_status": deliverable["review_status"],
        "validation_level": deliverable["scientific_validation_level"],
        "warnings": deliverable.get("warnings", []),
        "limitations": deliverable.get("limitations", []),
        "manifest_hash": deliverable.get("manifest_hash"),
        "report_checksum": report.get("checksum"),
        "associated_artifact_ids": deliverable.get("artifact_ids", []),
        "notice": "Delivery approval is separate from scientific validation and production readiness.",
    }
    path = Path(report["path"]).with_suffix(Path(report["path"]).suffix + ".delivery.json")
    path.write_text(json.dumps(sanitize_manifest_paths(metadata), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
