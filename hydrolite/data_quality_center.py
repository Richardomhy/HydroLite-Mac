from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import shutil
import zipfile

import pandas as pd

from hydrolite.data_registry import get_dataset_type
from hydrolite.data_upload import detect_file_format, detect_table_structure, inspect_uploaded_file
from hydrolite.field_mapping import apply_field_mapping, infer_field_mapping
from hydrolite.spatial_ingestion import inspect_crs, inspect_extent, validate_geometry
from hydrolite.raster_ingestion import validate_raster
from hydrolite.timeseries_ingestion import detect_duplicate_timestamps, detect_missing_timestamps, detect_timestamp_column, infer_time_interval, parse_timestamp_column
from hydrolite.workspace import calculate_file_checksum, read_workspace_manifest, write_workspace_manifest
from hydrolite.data_lineage import add_lineage_operation, create_lineage_record, validate_lineage_graph, write_lineage_manifest


def _load_table(path: Path) -> pd.DataFrame | None:
    fmt = detect_file_format(path)
    if fmt == "csv":
        return pd.read_csv(path)
    if fmt == "tsv":
        return pd.read_csv(path, sep="\t")
    if fmt == "xlsx":
        return None
    return None


def calculate_dataset_quality_score(result: dict[str, Any]) -> int:
    deductions = 35 * len(result.get("errors", [])) + 10 * len(result.get("warnings", []))
    return max(0, 100 - deductions)


def classify_dataset_quality(result: dict[str, Any]) -> str:
    if result.get("format") == "unsupported":
        return "unsupported"
    if result.get("errors"):
        return "invalid"
    if result.get("mapping_status") == "needs_mapping":
        return "needs_mapping"
    if result.get("mapping_status") == "needs_confirmation":
        return "needs_mapping"
    return "ready_with_warnings" if result.get("warnings") else "ready"


def run_dataset_quality_checks(dataset_id: str, workspace_dir: str | Path) -> dict[str, Any]:
    root = Path(workspace_dir).expanduser().resolve()
    manifest = read_workspace_manifest(root)
    record = next((item for item in manifest.get("datasets", []) if item["dataset_id"] == dataset_id), None)
    if record is None:
        raise KeyError(f"Unknown dataset_id: {dataset_id}")
    raw = root / record["raw_path"]
    inspection = inspect_uploaded_file(raw)
    dataset_type = record.get("user_declared_type") or record.get("classification", {}).get("dataset_type", "unknown")
    errors: list[str] = []
    warnings: list[str] = []
    mapping_status = "not_applicable"
    mapping: dict[str, str] = {}
    frame = _load_table(raw)
    if dataset_type != "unknown" and frame is not None:
        inferred = infer_field_mapping(frame, dataset_type)
        mapping_status = inferred["status"]
        mapping = inferred["mapping"]
        if mapping_status == "needs_mapping":
            errors.append(f"Required fields need mapping: {', '.join(inferred['missing_required'])}")
        elif mapping_status == "needs_confirmation":
            warnings.append("Field mapping needs user confirmation.")
        standardized_frame = apply_field_mapping(frame, mapping)
        timestamp = detect_timestamp_column(standardized_frame)
        if timestamp:
            standardized_frame = parse_timestamp_column(standardized_frame, timestamp)
            if standardized_frame[timestamp].isna().any():
                errors.append("Some timestamps cannot be parsed.")
            if detect_duplicate_timestamps(standardized_frame, timestamp):
                errors.append("Duplicate timestamps detected.")
            if detect_missing_timestamps(standardized_frame, timestamp):
                warnings.append("Missing timestamps detected.")
            if infer_time_interval(standardized_frame, timestamp).get("status") == "irregular":
                warnings.append("Irregular time interval detected.")
        for column in ("rainfall_mm", "precipitation_mm", "flow_cms", "area_km2"):
            if column in standardized_frame:
                values = pd.to_numeric(standardized_frame[column], errors="coerce")
                if values.isna().any():
                    errors.append(f"{column} contains invalid numeric values.")
                if column in {"rainfall_mm", "precipitation_mm", "flow_cms"} and (values < 0).any():
                    errors.append(f"{column} contains negative values.")
    elif inspection["format"] in {"geojson", "zip_shapefile", "gpkg", "kml", "kmz"}:
        crs = inspect_crs(raw)
        if crs["status"] == "crs_missing":
            errors.append("CRS is missing; user confirmation is required.")
        geometry = validate_geometry(raw)
        if geometry["status"] == "invalid":
            errors.append("Invalid or empty geometry detected.")
        if geometry["status"] == "optional_backend_required":
            warnings.append("Full geometry validation requires optional GIS dependencies or qgis_process.")
        mapping_status = "needs_confirmation" if record.get("classification", {}).get("confidence", 0) < 0.9 else "passed"
    elif inspection["format"] in {"geotiff", "ascii_grid", "netcdf", "hdf5"}:
        raster = validate_raster(raw, dataset_type)
        warnings.extend(raster.get("warnings", []))
        if raster.get("status") == "optional_backend_required":
            warnings.append(f"{inspection['format']} inspection requires an optional backend.")
    elif inspection["format"] == "unsupported":
        errors.append("Unsupported file format.")
    result = {
        "dataset_id": dataset_id, "dataset_type": dataset_type, "format": inspection["format"], "errors": errors,
        "warnings": warnings, "mapping_status": mapping_status, "mapping": mapping, "raw_path": record["raw_path"],
        "provenance": "recorded" if record.get("checksum") else "missing",
    }
    result["quality_status"] = classify_dataset_quality(result)
    result["quality_score"] = calculate_dataset_quality_score(result)
    if result["quality_status"] in {"ready", "ready_with_warnings"} and frame is not None and mapping:
        standardized = root / "standardized" / raw.name
        standardized.parent.mkdir(parents=True, exist_ok=True)
        apply_field_mapping(frame, mapping).to_csv(standardized.with_suffix(".csv"), index=False)
        standardized = standardized.with_suffix(".csv")
        child_id = f"{dataset_id}_standardized"
        add_lineage_operation(dataset_id, child_id, "field_mapping", root, source_checksum=record["checksum"], output_checksum=calculate_file_checksum(standardized), parameters={"mapping": mapping}, reproducible_command=f"python -m hydrolite data quality {root.name}")
        record["standardized_path"] = str(standardized.relative_to(root))
    elif result["quality_status"] in {"ready", "ready_with_warnings"} and inspection["format"] == "geojson":
        standardized = root / "standardized" / raw.name
        shutil.copy2(raw, standardized)
        child_id = f"{dataset_id}_standardized"
        add_lineage_operation(dataset_id, child_id, "quality_filter", root, source_checksum=record["checksum"], output_checksum=calculate_file_checksum(standardized), reproducible_command=f"python -m hydrolite data quality {root.name}")
        record["standardized_path"] = str(standardized.relative_to(root))
    record["quality_status"] = result["quality_status"]
    record["processing_status"] = "standardized" if record.get("standardized_path") else "quality_checked"
    if not any(row.get("child_id") == dataset_id and row.get("operation") == "upload" for row in validate_lineage_graph(root)["records"]):
        records = validate_lineage_graph(root)["records"]
        records.insert(0, create_lineage_record(record))
        (root / "lineage" / "lineage_manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    write_workspace_manifest(root, manifest)
    return result


def build_quality_issue_table(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for result in results:
        rows.extend({"dataset_id": result["dataset_id"], "quality_status": result["quality_status"], "severity": "error", "message": message} for message in result.get("errors", []))
        rows.extend({"dataset_id": result["dataset_id"], "quality_status": result["quality_status"], "severity": "warning", "message": message} for message in result.get("warnings", []))
    return pd.DataFrame(rows, columns=["dataset_id", "quality_status", "severity", "message"])


def run_workspace_quality_checks(workspace_dir: str | Path) -> dict[str, Any]:
    root = Path(workspace_dir).expanduser().resolve()
    manifest = read_workspace_manifest(root)
    results = [run_dataset_quality_checks(item["dataset_id"], root) for item in manifest.get("datasets", [])]
    status = "ready" if results and all(item["quality_status"] == "ready" for item in results) else ("ready_with_warnings" if results and all(item["quality_status"] in {"ready", "ready_with_warnings"} for item in results) else ("incomplete" if not results else "needs_repair"))
    return {"status": status, "workspace_dir": str(root), "dataset_count": len(results), "datasets": results, "issues": build_quality_issue_table(results)}


def write_data_quality_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = output / "data_quality_summary.xlsx"
    report = output / "data_quality_report.md"
    with pd.ExcelWriter(summary) as writer:
        pd.DataFrame([{key: value for key, value in row.items() if key not in {"errors", "warnings", "mapping"}} for row in result["datasets"]]).to_excel(writer, sheet_name="datasets", index=False)
        result["issues"].to_excel(writer, sheet_name="issues", index=False)
    report.write_text(f"# Data Quality Report\n\n- Status: `{result['status']}`\n- Datasets: `{result['dataset_count']}`\n- Issues: `{len(result['issues'])}`\n", encoding="utf-8")
    return {"xlsx": summary, "markdown": report}


def export_data_quality_bundle(output_dir: str | Path) -> Path:
    root = Path(output_dir)
    bundle = root / "data_quality_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.glob("data_quality_*"):
            if path.is_file() and path != bundle:
                archive.write(path, path.name)
    return bundle
