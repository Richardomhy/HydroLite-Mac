from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

import pandas as pd

from hydrolite.connectors import get_connector
from hydrolite.data_requirements import build_project_data_requirement_matrix
from hydrolite.connectors.contracts import FetchedDataset, DataRequirement
from hydrolite.workspace import write_workspace_manifest, calculate_file_checksum


def select_best_data_source(dataset_type: str, context: dict[str, Any]) -> str:
    preferred = {
        "dem": "gee", "rainfall_forecast": "gee", "temperature": "cds",
        "ICESat2_ATL13": "earthdata", "land_use": "gee", "satellite_image": "stac",
    }
    return preferred.get(dataset_type, "local")


def import_fetched_dataset(fetched: dict[str, Any], workspace_dir: str | Path, requirement: DataRequirement) -> dict[str, Any]:
    """Import inert cache content to the existing workspace; QC/mapping stays in Data Center."""
    root = Path(workspace_dir).expanduser().resolve()
    path = Path(fetched.get("local_path", "")).resolve()
    if not path.is_file() or not fetched.get("checksum") or calculate_file_checksum(path) != fetched["checksum"]:
        raise ValueError("Fetched artifact checksum is missing or invalid")
    record = {
        "dataset_id": "ds_" + fetched["checksum"][:12], "original_filename": path.name,
        "stored_filename": path.name, "source_type": "online_public", "source_platform": fetched.get("candidate", {}).get("provider"),
        "upload_time": fetched.get("retrieved_at"), "checksum": fetched["checksum"], "size": path.stat().st_size,
        "media_type": fetched.get("candidate", {}).get("content_type"), "detected_format": path.suffix.lstrip("."),
        "user_declared_type": requirement.data_type, "dataset_type": requirement.data_type,
        "coordinate_system": fetched.get("candidate", {}).get("crs"), "temporal_range": fetched.get("candidate", {}).get("temporal_extent"),
        "spatial_extent": fetched.get("candidate", {}).get("spatial_extent"), "units": {},
        "license": fetched.get("candidate", {}).get("license", "unknown"),
        "license_status": fetched.get("candidate", {}).get("license_status", "unknown"),
        "processing_status": "downloaded_needs_data_center_ingestion", "quality_status": "needs_mapping",
        "project_measurement_confirmed": False, "online_provenance": {"candidate": fetched.get("candidate"), "retrieved_at": fetched.get("retrieved_at"), "checksum": fetched["checksum"], "etag": fetched.get("etag"), "last_modified": fetched.get("last_modified"), "processing_chain": fetched.get("processing_chain", [])},
        "cache_reference": str(path), "standardized_path": None, "lineage_parent": None,
        "warnings": ["Download success is not QC or model readiness; import and review in Data Center."],
        "raw_path": str(path),
    }
    manifest_path = root / "workspace_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Workspace manifest is required before importing a fetched dataset")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing = next((item for item in manifest.get("datasets", []) if item.get("dataset_id") == record["dataset_id"]), None)
    if existing:
        return existing
    manifest.setdefault("datasets", []).append(record)
    write_workspace_manifest(root, manifest)
    from hydrolite.data_lineage import add_lineage_operation
    add_lineage_operation(fetched["candidate"].get("dataset_id", "online_source"), record["dataset_id"], "public_data_cached", root, source_checksum=fetched["checksum"], output_checksum=fetched["checksum"], parameters={"license_status": record["license_status"], "retrieved_at": record["upload_time"]}, warnings=record["warnings"], reproducible_command="python -m hydrolite data-connectors fetch --requirement <id>")
    return record


def canonical_online_table(frame, dataset_type, metadata):
    """Share existing field, CRS and time parsers; source units remain explicit."""
    from hydrolite.field_mapping import infer_field_mapping, apply_field_mapping
    from hydrolite.timeseries_ingestion import detect_timestamp_column, parse_timestamp_column
    mapped = infer_field_mapping(frame, dataset_type)
    standardized = apply_field_mapping(frame, mapped["mapping"])
    timestamp = detect_timestamp_column(standardized)
    if timestamp:
        standardized = parse_timestamp_column(standardized, timestamp)
    standardized.attrs["online_provenance"] = metadata
    standardized.attrs["mapping_status"] = mapped["status"]
    return standardized


def create_acquisition_plan(workspace_dir: str | Path, workflow_id: str) -> dict[str, Any]:
    matrix = build_project_data_requirement_matrix(workflow_id, workspace_dir)
    steps = []
    for _, row in matrix[matrix["status"] != "ready"].drop_duplicates("dataset_type").iterrows():
        connector = select_best_data_source(row["dataset_type"], {})
        steps.append({
            "step_id": f"acquire_{row['dataset_type']}", "dataset_type": row["dataset_type"], "source": connector,
            "status": "planned", "bbox": None, "start": None, "end": None, "estimated_size_mb": None,
            "license": "check source terms", "login_required": connector in {"gee", "earthdata", "cds"},
            "processing_steps": ["download", "quality_check", "standardize"], "output_format": "source_dependent",
            "user_confirmed": False, "execute": False,
        })
    return {"status": "planned", "workspace_dir": str(Path(workspace_dir).resolve()), "workflow_id": workflow_id, "created_at": datetime.now(timezone.utc).isoformat(), "steps": steps, "download_execute": False}


def estimate_acquisition_cost(plan: dict[str, Any]) -> dict[str, Any]:
    return {"estimated_cost": "unknown_or_free", "requires_user_review": True}


def estimate_acquisition_size(plan: dict[str, Any]) -> dict[str, Any]:
    values = [step["estimated_size_mb"] for step in plan["steps"] if step.get("estimated_size_mb") is not None]
    return {"estimated_size_mb": sum(values) if values else None, "unknown_steps": len(plan["steps"]) - len(values)}


def validate_acquisition_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors = []
    for step in plan.get("steps", []):
        if step.get("execute") and not step.get("user_confirmed"):
            errors.append(f"{step['step_id']}: execution requires user confirmation")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def execute_acquisition_step(step: dict[str, Any], execute: bool = False) -> dict[str, Any]:
    if not execute:
        return {**step, "status": "dry_run", "download_execute": False}
    if not step.get("user_confirmed"):
        return {**step, "status": "blocked_confirmation_required", "download_execute": False}
    return get_connector(step["source"]).download(step, execute=True)


def execute_acquisition_plan(plan: dict[str, Any], execute: bool = False) -> dict[str, Any]:
    return {"status": "dry_run" if not execute else "completed_with_connector_results", "download_execute": execute, "steps": [execute_acquisition_step(step, execute) for step in plan.get("steps", [])]}


def write_acquisition_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "acquisition_plan.json"
    xlsx_path = output / "acquisition_plan.xlsx"
    md_path = output / "acquisition_report.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame(result.get("steps", [])).to_excel(xlsx_path, index=False)
    md_path.write_text(f"# Data Acquisition Plan\n\n- Status: `{result['status']}`\n- Steps: `{len(result.get('steps', []))}`\n- Automatic download: `False`\n", encoding="utf-8")
    return {"json": json_path, "xlsx": xlsx_path, "markdown": md_path}
