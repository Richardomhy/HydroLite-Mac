from __future__ import annotations

from pathlib import Path
import json

import pandas as pd


def validate_table_artifact(path: str | Path) -> dict:
    source = Path(path)
    try:
        frame = pd.read_csv(source) if source.suffix.lower() == ".csv" else pd.read_excel(source)
    except Exception as exc:
        return {"path": str(source), "status": "invalid", "message": str(exc)}
    status = "valid_with_warnings" if frame.empty else "valid"
    return {"path": str(source), "status": status, "rows": len(frame), "columns": list(frame.columns)}


def validate_timeseries_artifact(path: str | Path) -> dict:
    result = validate_table_artifact(path)
    if result["status"] == "invalid": return result
    candidates = [str(column) for column in result["columns"] if any(word in str(column).lower() for word in ("time", "date", "datetime"))]
    if not candidates:
        result.update(status="incomplete", message="No time column detected.")
    return result


def validate_vector_artifact(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        valid = data.get("type") in {"FeatureCollection", "Feature"}
        return {"path": str(path), "status": "valid" if valid else "invalid", "feature_count": len(data.get("features", []))}
    except Exception as exc:
        return {"path": str(path), "status": "invalid", "message": str(exc)}


def validate_raster_artifact(path: str | Path) -> dict:
    from hydrolite.raster_ingestion import inspect_raster
    result = inspect_raster(path)
    return {"path": str(path), "status": "valid" if result.get("status") == "passed" else "unavailable_backend", "details": result}


def validate_report_artifact(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return {"path": str(source), "status": "invalid", "message": "Report is missing or empty."}
    return {"path": str(source), "status": "valid", "size": source.stat().st_size}


def validate_model_output_artifact(path: str | Path, model_id: str) -> dict:
    result = validate_table_artifact(path)
    result["model_id"] = model_id
    return result


def validate_run_artifacts(run_id: str) -> dict:
    from hydrolite.artifact_store import list_artifact_records
    results = []
    for artifact in list_artifact_records(run_id=run_id):
        path, kind = Path(artifact["path"]), artifact["artifact_type"]
        if kind in {"table", "timeseries"}:
            result = validate_timeseries_artifact(path) if kind == "timeseries" else validate_table_artifact(path)
        elif kind == "vector":
            result = validate_vector_artifact(path)
        elif kind == "raster":
            result = validate_raster_artifact(path)
        elif kind == "log":
            result = {"path": str(path), "status": "valid" if path.exists() else "invalid", "size": path.stat().st_size if path.exists() else 0}
        elif kind in {"report", "manifest", "configuration"}:
            result = validate_report_artifact(path)
        else:
            result = {"path": str(path), "status": "unchecked"}
        results.append({"artifact_id": artifact["artifact_id"], **result})
    return {"run_id": run_id, "status": calculate_artifact_quality_summary(results), "results": results}


def calculate_artifact_quality_summary(results: list[dict]) -> str:
    statuses = {row["status"] for row in results}
    if "invalid" in statuses: return "invalid"
    if "incomplete" in statuses: return "incomplete"
    if statuses & {"valid_with_warnings", "unavailable_backend", "unchecked"}: return "valid_with_warnings"
    return "valid" if results else "incomplete"


def write_artifact_validation_report(output_dir: str | Path, result: dict) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    xlsx = output / "artifact_validation.xlsx"
    md = output / "artifact_validation.md"
    pd.DataFrame(result["results"]).to_excel(xlsx, index=False)
    md.write_text(f"# Artifact Validation\n\n- Run: `{result['run_id']}`\n- Status: `{result['status']}`\n- Artifacts: `{len(result['results'])}`\n", encoding="utf-8")
    return {"xlsx": xlsx, "markdown": md}
