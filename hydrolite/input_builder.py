from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import shutil

import pandas as pd
import yaml

from hydrolite.data_lineage import add_lineage_operation, validate_lineage_graph
from hydrolite.workspace import calculate_file_checksum, read_workspace_manifest


def _eligible(workspace_dir: str | Path) -> dict[str, Path]:
    root = Path(workspace_dir).expanduser().resolve()
    result = {}
    for item in read_workspace_manifest(root).get("datasets", []):
        relative = item.get("standardized_path")
        dataset_type = item.get("user_declared_type") or item.get("classification", {}).get("dataset_type")
        if relative and dataset_type:
            path = root / relative
            if path.is_file() and (root / "standardized") in path.parents:
                result[dataset_type] = path
    return result


def _copy_input(source: Path, target: Path, workspace_dir: Path, dataset_type: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    parent = next((item["dataset_id"] for item in read_workspace_manifest(workspace_dir).get("datasets", []) if item.get("standardized_path") and workspace_dir / item["standardized_path"] == source), dataset_type)
    add_lineage_operation(parent, f"model_input_{dataset_type}", "model_input_generation", workspace_dir, source_checksum=calculate_file_checksum(source), output_checksum=calculate_file_checksum(target), parameters={"target": target.name}, reproducible_command="python -m hydrolite data build-inputs <workspace>")
    return target


def build_hydrolite_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    root, output = Path(workspace_dir).resolve(), Path(output_dir).resolve() / "hydrolite"
    available = _eligible(root)
    aliases = {"rainfall_observed": "rainfall.csv", "subbasins": "subbasins.csv", "reaches": "reaches.csv", "streamflow_observed": "observed_streamflow.csv", "watershed_boundary": "watershed_boundary.geojson"}
    files = {kind: str(_copy_input(available[kind], output / name, root, kind)) for kind, name in aliases.items() if kind in available}
    required = {"rainfall_observed", "subbasins", "reaches"}
    missing = sorted(required - set(files))
    return {"model_id": "hydrolite_event_model", "status": "ready" if not missing else "incomplete", "files": files, "missing": missing}


def build_hec_hms_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    hydro = build_hydrolite_inputs(workspace_dir, output_dir)
    return {"model_id": "hec_hms_event_model", "status": "ready_for_project_generation" if hydro["status"] == "ready" else "incomplete", "source": hydro, "note": "HEC-HMS execution remains a separate local step."}


def build_swmm_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    available = _eligible(workspace_dir)
    if "swmm_inp" not in available:
        return {"model_id": "swmm", "status": "incomplete", "missing": ["swmm_inp"]}
    path = _copy_input(available["swmm_inp"], Path(output_dir) / "swmm" / "working.inp", Path(workspace_dir).resolve(), "swmm_inp")
    return {"model_id": "swmm", "status": "ready_for_working_copy", "files": {"working_inp": str(path)}}


def build_watershed_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    available = _eligible(workspace_dir)
    missing = [name for name in ("dem", "outlet_points") if name not in available]
    return {"model_id": "watershed_delineation", "status": "ready" if not missing else "incomplete", "missing": missing}


def build_rusle_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    available = _eligible(workspace_dir)
    required = {"dem", "RUSLE_R", "RUSLE_K", "RUSLE_C", "RUSLE_P"}
    missing = sorted(required - set(available))
    return {"model_id": "rusle", "status": "ready" if not missing else "incomplete", "missing": missing}


def build_reservoir_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    available = _eligible(workspace_dir)
    missing = [name for name in ("stage_area_volume", "stage_discharge") if name not in available]
    return {"model_id": "reservoir_routing", "status": "ready" if not missing else "incomplete", "missing": missing}


def build_flood_forecast_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    available = _eligible(workspace_dir)
    source = next((available[name] for name in ("rainfall_forecast", "rainfall_observed") if name in available), None)
    if source is None:
        return {"model_id": "flood_forecast", "status": "incomplete", "missing": ["rainfall_forecast or rainfall_observed"]}
    path = _copy_input(source, Path(output_dir) / "flood_forecast" / "rainfall_input.csv", Path(workspace_dir).resolve(), "rainfall_forecast")
    return {"model_id": "flood_forecast", "status": "ready_scenario_input", "files": {"rainfall": str(path)}}


def build_continuous_drought_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    root, output = Path(workspace_dir).resolve(), Path(output_dir).resolve() / "drought"
    available = _eligible(root)
    aliases = {
        "daily_meteorology": "daily_meteorology.csv",
        "potential_evapotranspiration": "potential_evapotranspiration.csv",
        "soil_moisture_observed": "observed_soil_moisture.csv",
        "groundwater_storage": "observed_groundwater.csv",
        "streamflow_observed": "observed_streamflow.csv",
        "reservoir_daily_balance": "observed_reservoir.csv",
        "vegetation_index_timeseries": "vegetation_index_timeseries.csv",
        "climate_forecast_ensemble": "climate_forecast_ensemble.csv",
        "drought_scenario": "drought_scenario.csv",
    }
    files = {kind: str(_copy_input(available[kind], output / name, root, kind)) for kind, name in aliases.items() if kind in available}
    missing = [] if "daily_meteorology" in files else ["daily_meteorology"]
    return {"model_id": "continuous_hydrology_drought", "status": "ready" if not missing else "incomplete", "files": files, "missing": missing}


def build_future_water_quality_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    available = _eligible(workspace_dir)
    missing = [name for name in ("water_quality_observations", "streamflow_observed") if name not in available]
    return {"model_id": "water_quality", "status": "planned_interface_ready" if not missing else "incomplete", "missing": missing}


def validate_generated_inputs(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    files = [path for path in root.rglob("*") if path.is_file()]
    raw = [str(path) for path in files if "raw" in path.parts]
    return {"status": "passed" if files and not raw else "failed", "file_count": len(files), "raw_inputs": raw}


def write_input_build_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx = output / "input_build_summary.xlsx"
    md = output / "input_build_report.md"
    pd.DataFrame([{key: value for key, value in row.items() if key not in {"files", "source"}} for row in result["models"]]).to_excel(xlsx, index=False)
    md.write_text("# Model Input Build\n\n" + "\n".join(f"- {row['model_id']}: `{row['status']}`" for row in result["models"]) + "\n", encoding="utf-8")
    return {"xlsx": xlsx, "markdown": md}


def build_all_inputs(workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    models = [
        build_hydrolite_inputs(workspace_dir, output),
        build_hec_hms_inputs(workspace_dir, output),
        build_swmm_inputs(workspace_dir, output),
        build_watershed_inputs(workspace_dir, output),
        build_rusle_inputs(workspace_dir, output),
        build_reservoir_inputs(workspace_dir, output),
        build_flood_forecast_inputs(workspace_dir, output),
        build_continuous_drought_inputs(workspace_dir, output),
        build_future_water_quality_inputs(workspace_dir, output),
    ]
    result = {"status": "completed", "created_at": datetime.now(timezone.utc).isoformat(), "workspace_dir": str(Path(workspace_dir).resolve()), "models": models}
    result["outputs"] = {key: str(value) for key, value in write_input_build_report(output, result).items()}
    result["validation"] = validate_generated_inputs(output)
    result["lineage"] = validate_lineage_graph(workspace_dir)
    return result
