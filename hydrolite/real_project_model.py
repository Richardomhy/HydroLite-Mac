"""M8B real-project HydroLite run, diagnostic validation, and delivery orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable
import hashlib
import json
import platform
import re
import subprocess
import sys
import uuid

import numpy as np
import pandas as pd
import yaml

from hydrolite.__version__ import __version__
from hydrolite.artifact_store import register_artifact
from hydrolite.capability_registry import get_capability
from hydrolite.delivery_review import create_deliverable, review_delivery, submit_delivery
from hydrolite.deliverable_manifest import write_deliverable_manifest
from hydrolite.integrity_verification import verify_deliverable
from hydrolite.input_builder import build_hydrolite_inputs
from hydrolite.metrics import calculate_all_metrics
from hydrolite.project_versioning import (
    capture_delivery_environment,
    compare_project_versions,
    create_project_version,
    resolve_project,
)
from hydrolite.runner import run_case
from hydrolite.runtime_db import create_run_record, list_project_version_records, update_run_record
from hydrolite.runtime_paths import ensure_runtime_directories
from hydrolite.workspace import read_workspace_manifest, write_workspace_manifest


ANALYSIS_CRS = "EPSG:32649"
MODEL_EVENT = "event_20260622_25"
MAY_EVENT = "event_20260525_26"
SCENARIO_FACTORS = (0.8, 1.0, 1.2, 1.5)
OUTPUTS = {
    "basin": "basin/basin_summary.xlsx",
    "topology": "basin/topology_validation.json",
    "geometry": "basin/geometry_processing.xlsx",
    "input_manifest": "inputs/hydrolite_input_manifest.json",
    "parameters": "inputs/parameter_provenance.xlsx",
    "events": "events/real_event_catalog.xlsx",
    "readiness": "events/event_readiness.xlsx",
    "run_manifest": "runs/hydrolite_real_run_manifest.json",
    "metrics": "validation/event_metrics.xlsx",
    "validation": "validation/validation_summary.xlsx",
    "aligned": "validation/observed_vs_simulated.csv",
    "scenarios": "scenarios/scenario_comparison.xlsx",
    "wet_weather": "water_quality/wet_weather_event_diagnostic.xlsx",
    "loads": "water_quality/instantaneous_load_diagnostic.xlsx",
    "friction": "product/friction_closure.xlsx",
    "versions": "delivery/version_comparison.xlsx",
    "report_zh": "reports/m8b_real_model_validation_report_zh.md",
    "report_en": "reports/m8b_real_model_validation_report_en.md",
    "manifest": "reports/m8b_manifest.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=False, timeout=10,
    ).stdout.strip()


def _safe_json(value: Any) -> Any:
    if isinstance(value, Path):
        return value.name
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if pd.isna(value) if not isinstance(value, (str, bool)) else False:
        return None
    return value


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_safe_json(payload), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path


def _write_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    return path


def _find_unique(root: Path, name: str) -> Path:
    paths = [path for path in root.rglob(name) if path.is_file()]
    if len(paths) != 1:
        raise FileNotFoundError(f"Expected one {name!r} under source root, found {len(paths)}")
    return paths[0]


def _logical(root: Path, path: Path) -> str:
    return f"source-root/{path.relative_to(root).as_posix()}"


def _snapshot_rows(root: Path, paths: Iterable[Path]) -> pd.DataFrame:
    rows = []
    seen: set[str] = set()
    for path in dict.fromkeys(Path(item).resolve() for item in paths):
        stat = path.stat()
        checksum = _hash_file(path)
        dataset_id = f"real_{checksum[:16]}"
        if dataset_id in seen:
            dataset_id += f"_{hashlib.sha256(_logical(root, path).encode()).hexdigest()[:8]}"
        seen.add(dataset_id)
        rows.append({
            "logical_path": _logical(root, path), "dataset_id": dataset_id,
            "checksum": checksum, "modified_time_ns": stat.st_mtime_ns, "size": stat.st_size,
        })
    return pd.DataFrame(rows)


def guard_external_sources(
    source_root: str | Path,
    inventory: pd.DataFrame,
    paths: Iterable[str | Path] | dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Reject changed referenced inputs before a governed model run."""
    root = Path(source_root).expanduser().resolve()
    logical_column = "logical_path" if "logical_path" in inventory else "source"
    if logical_column not in inventory or "checksum" not in inventory:
        raise ValueError("External inventory requires source/logical_path and checksum fields")
    by_path = inventory.set_index(logical_column, drop=False)
    by_dataset = inventory.set_index("dataset_id", drop=False) if "dataset_id" in inventory else pd.DataFrame()
    checked = []
    candidates = list(paths.items()) if isinstance(paths, dict) else [(None, value) for value in (paths or inventory[logical_column].tolist())]
    for dataset_id, value in candidates:
        path = Path(value)
        logical = str(value)
        if not path.is_absolute():
            logical = logical.removeprefix("source-root/")
            path = root / logical
            logical = f"source-root/{logical}"
        else:
            logical = _logical(root, path)
        expected = by_dataset.loc[dataset_id] if dataset_id in by_dataset.index else (by_path.loc[logical] if logical in by_path.index else None)
        if expected is None or not path.is_file():
            raise RuntimeError(f"external_data_changed_since_snapshot: missing {logical}")
        checksum = _hash_file(path)
        mtime_changed = False
        if "modified_time_ns" in expected and pd.notna(expected["modified_time_ns"]):
            mtime_changed = path.stat().st_mtime_ns != int(expected["modified_time_ns"])
        elif "modified_time" in expected and pd.notna(expected["modified_time"]):
            expected_mtime = pd.Timestamp(expected["modified_time"]).timestamp()
            mtime_changed = abs(path.stat().st_mtime - expected_mtime) > 1e-6
        if checksum != str(expected["checksum"]) or mtime_changed:
            raise RuntimeError(f"external_data_changed_since_snapshot: {logical}")
        checked.append(logical)
    return {"status": "passed", "checked": checked}


def _normalize_name(value: Any) -> str:
    return re.sub(r"(新版|旧版|汇总)$", "", str(value).strip())


def _selection_priority(value: Any) -> int:
    name = str(value).strip()
    return 3 if name.endswith("新版") else 2 if name.endswith("汇总") else 0 if name.endswith("旧版") else 1


def _shapefile_components(path: Path) -> list[Path]:
    return sorted(item for item in path.parent.glob(f"{path.stem}.*") if item.is_file())


def _required_source_paths(source: Path) -> list[Path]:
    polygon = _find_unique(source, "高桥河汇总_面.shp")
    lines = _find_unique(source, "高桥河汇总_线.shp")
    names = (
        "eight_area_master_updated.csv", "outlets_wgs84.csv",
        "降雨水位流量小时序列_20260622_25.csv", "event_flow_preliminary_calibration.csv",
        "observed_flow_event_20260525_20260526.csv", "20260623_24水样检测结果规范化.csv",
        "20260623_24雨天补充采样瞬时通量.csv", "build_full_source_report.py",
    )
    return [*[_find_unique(source, name) for name in names], *_shapefile_components(polygon), *_shapefile_components(lines)]


def _register_processed_inputs(workspace: Path, inputs: dict[str, Any], basin: dict[str, Any]) -> None:
    workspace = workspace.resolve()
    manifest = read_workspace_manifest(workspace)
    entries = [
        (Path(inputs["data_dir"]) / "rainfall.csv", "rainfall_observed", False),
        (Path(inputs["data_dir"]) / "observed_streamflow.csv", "streamflow_observed", True),
        (Path(inputs["data_dir"]) / "subcatchments.csv", "subbasins", False),
        (Path(inputs["data_dir"]) / "reaches.csv", "reaches", False),
        *((path, "processed_vector", False) for path in basin["processed"]),
    ]
    existing = {row.get("dataset_id") for row in manifest.get("datasets", [])}
    for path, dataset_type, sensitive in entries:
        dataset_id = f"m8b_{_hash_file(path)[:16]}"
        if dataset_id in existing:
            continue
        manifest.setdefault("datasets", []).append({
            "dataset_id": dataset_id, "dataset_type": dataset_type,
            "user_declared_type": dataset_type, "logical_path": str(path.relative_to(workspace)),
            "processed_path": str(path.relative_to(workspace)), "standardized_path": str(path.relative_to(workspace)),
            "checksum": _hash_file(path), "size": path.stat().st_size,
            "quality_status": "ready_with_warnings", "source_type": "processed_derivative", "sensitive": sensitive,
        })
    write_workspace_manifest(workspace, manifest)


def _apply_input_builder(workspace: Path, inputs: dict[str, Any], output: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    built = build_hydrolite_inputs(workspace, workspace / "models" / "m8b")
    if built["status"] != "ready":
        raise RuntimeError(f"HydroLite Input Builder did not produce a runnable input set: {built['missing']}")
    files = {key: Path(value) for key, value in built["files"].items()}
    case = yaml.safe_load(inputs["case"].read_text(encoding="utf-8"))
    input_dir = files["rainfall_observed"].parent
    case["inputs"] = {
        "directory": str(input_dir),
        "rainfall": files["rainfall_observed"].name,
        "subcatchments": files["subbasins"].name,
        "reaches": files["reaches"].name,
    }
    if "streamflow_observed" in files:
        case["observed"]["observed_streamflow_csv"] = str(files["streamflow_observed"])
    inputs["case"].write_text(yaml.safe_dump(case, sort_keys=False, allow_unicode=True), encoding="utf-8")
    inputs["model_input_dir"] = input_dir
    inputs["input_builder"] = built
    inputs["manifest"]["input_builder"] = {
        "status": built["status"],
        "model_id": built["model_id"],
        "files": {key: f"project/{path.relative_to(workspace).as_posix()}" for key, path in files.items()},
    }
    inputs["manifest"]["processed_checksums"][inputs["case"].name] = _hash_file(inputs["case"])
    _write_json(output / OUTPUTS["input_manifest"], inputs["manifest"])
    return built


def build_basin_definition(source_root: str | Path, workspace_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Build processed GIS derivatives and an aggregate outlet topology."""
    import geopandas as gpd
    import pyogrio

    source = Path(source_root).expanduser().resolve()
    workspace = Path(workspace_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    area_path = _find_unique(source, "eight_area_master_updated.csv")
    polygon_path = _find_unique(source, "高桥河汇总_面.shp")
    line_path = _find_unique(source, "高桥河汇总_线.shp")
    outlet_path = _find_unique(source, "outlets_wgs84.csv")
    sources = [area_path, *_shapefile_components(polygon_path), *_shapefile_components(line_path), outlet_path]
    snapshot = _snapshot_rows(source, sources)

    areas = pd.read_csv(area_path)
    required = {"basin", "area_km2", "elevation_min_m", "elevation_mean_m", "elevation_max_m", "slope_mean_deg"}
    if required - set(areas):
        raise ValueError(f"Basin summary missing fields: {sorted(required - set(areas))}")
    if len(areas) != 8 or areas["basin"].duplicated().any() or (areas["area_km2"] <= 0).any():
        raise ValueError("Reviewed basin summary must contain eight unique positive-area basins")

    polygons = gpd.read_file(polygon_path)
    source_crs = str(polygons.crs)
    selected = polygons.assign(
        _normalized=polygons["名称|name"].map(_normalize_name),
        _priority=polygons["名称|name"].map(_selection_priority),
    )
    selected = selected[selected["_normalized"].isin(set(areas["basin"]))].copy()
    selected = selected.sort_values(["_normalized", "_priority"]).drop_duplicates("_normalized", keep="last")
    if set(selected["_normalized"]) != set(areas["basin"]):
        raise ValueError("Reviewed eight-basin names could not be matched to source polygons")
    selected["subbasin_id"] = selected["_normalized"]
    selected = selected.to_crs(ANALYSIS_CRS)
    selected["geometry_area_km2"] = selected.geometry.area / 1_000_000.0
    processed_dir = workspace / "derived" / "m8b"
    processed_dir.mkdir(parents=True, exist_ok=True)
    polygon_copy = processed_dir / "reviewed_subbasins.geojson"
    selected.drop(columns=["_normalized", "_priority"]).to_file(polygon_copy, driver="GeoJSON")

    raw_lines = pyogrio.read_dataframe(line_path, on_invalid="ignore")
    line_before = len(raw_lines)
    null_before = int(raw_lines.geometry.isna().sum())
    valid_lines = raw_lines.dropna(subset=["geometry"]).to_crs(ANALYSIS_CRS)
    line_copy = processed_dir / "reviewed_river_lines.geojson"
    valid_lines.to_file(line_copy, driver="GeoJSON")

    outlets = pd.read_csv(outlet_path)
    outlet = outlets.loc[outlets["name"].eq("S-09-B")]
    if len(outlet) != 1:
        raise ValueError("A unique reviewed project outlet is required")
    stations = outlets.copy()
    station_map = stations[["name", "basin", "lon", "lat", "type"]].rename(columns={"name": "station_id"})
    station_map["subbasin_id"] = station_map["basin"]
    station_map["reach_id"] = "R_OUTLET"
    station_map["mapping_method"] = "reviewed source table plus basin-name match"
    station_map["mapping_confidence"] = np.where(station_map["station_id"].eq("S-09-B"), "high", "medium_requires_confirmation")
    station_map["distance_to_mapped_element_m"] = np.where(station_map["station_id"].eq("S-09-B"), 0.0, pd.NA)
    station_map["manual_confirmation"] = station_map["station_id"].eq("S-09-B")
    station_map["provenance_dataset_id"] = f"real_{_hash_file(outlet_path)[:16]}"

    subbasins = areas.copy()
    subbasins["subbasin_id"] = subbasins["basin"]
    subbasins["reach_id"] = "R_OUTLET"
    subbasins["crs"] = ANALYSIS_CRS
    subbasins["source_type"] = "GIS_derived"
    subbasins["source_dataset"] = f"real_{_hash_file(area_path)[:16]}"
    subbasins["land_use_summary_status"] = "not_used_for_initial_parameters"
    subbasins["soil_summary_status"] = "not_used_for_initial_parameters"
    reaches = pd.DataFrame([{
        "reach_id": "R_OUTLET", "downstream_reach_id": "OUTLET", "outlet_id": "S-09-B",
        "topology_role": "aggregate contributing areas to reviewed model outlet", "cycle": False,
        "topology_confidence": "diagnostic_only", "length_km": float(valid_lines.geometry.length.sum() / 1000),
        "slope": pd.NA, "source_type": "GIS_derived", "mapping_status": "aggregate_not_source_branch_topology",
    }])
    watershed = pd.DataFrame([{
        "watershed_id": "gaoqiao_reviewed_eight_area", "area_km2": float(areas["area_km2"].sum()),
        "analysis_crs": ANALYSIS_CRS, "source_crs": source_crs, "outlet_id": "S-09-B",
        "outlet_lon": float(outlet.iloc[0]["lon"]), "outlet_lat": float(outlet.iloc[0]["lat"]),
    }])
    relations = subbasins[["subbasin_id", "reach_id"]].copy()
    provenance = snapshot.copy()
    provenance["processing_step"] = provenance["logical_path"].map(
        lambda value: "select/reproject/export copy" if polygon_path.stem in value else
        "drop unreadable geometry/reproject/export copy" if line_path.stem in value else
        "attribute standardization" if value.endswith(area_path.name) else "reviewed station mapping"
    )
    provenance["processed_derivative"] = provenance["logical_path"].map(
        lambda value: polygon_copy.name if polygon_path.stem in value else
        line_copy.name if line_path.stem in value else
        "subbasin attributes" if value.endswith(area_path.name) else "station mapping"
    )
    provenance["raw_modified"] = False

    gis_area = float(selected["geometry_area_km2"].sum())
    tabular_area = float(areas["area_km2"].sum())
    area_difference_percent = (gis_area - tabular_area) / tabular_area * 100
    watershed["geometry_area_km2"] = gis_area
    watershed["area_difference_percent"] = area_difference_percent
    watershed["area_review_status"] = "manual_review_required" if abs(area_difference_percent) > 1 else "passed"

    basin_book = output / OUTPUTS["basin"]
    _write_excel(basin_book, {
        "watershed": watershed, "subbasins": subbasins, "reaches": reaches,
        "outlet": outlet, "stations": station_map, "relations": relations, "provenance": provenance,
    })
    geometry = pd.DataFrame([
        {"dataset": "reviewed_subbasins", "repair_method": "none; select and reproject copy", "before_count": len(polygons), "invalid_before": int((~polygons.geometry.is_valid).sum()), "after_count": len(selected), "invalid_after": int((~selected.geometry.is_valid).sum()), "area_change_percent": area_difference_percent, "length_change_percent": pd.NA, "validity_status": watershed.iloc[0]["area_review_status"]},
        {"dataset": "reviewed_river_lines", "repair_method": "invalid WKB read as null then omitted from processed copy", "before_count": line_before, "invalid_before": null_before, "after_count": len(valid_lines), "invalid_after": int(valid_lines.geometry.isna().sum()), "area_change_percent": pd.NA, "length_change_percent": pd.NA, "validity_status": "passed_with_one_omitted_feature_length_change_not_computable"},
    ])
    area_details = selected[["subbasin_id", "geometry_area_km2"]].merge(
        areas[["basin", "area_km2"]], left_on="subbasin_id", right_on="basin", how="left"
    )
    area_details["difference_percent"] = (area_details["geometry_area_km2"] - area_details["area_km2"]) / area_details["area_km2"] * 100
    area_details["review_status"] = np.where(area_details["difference_percent"].abs() > 1, "manual_review_required", "passed")
    _write_excel(output / OUTPUTS["geometry"], {"geometry_processing": geometry, "subbasin_area_review": area_details})
    topology = {
        "status": "passed_diagnostic_aggregate_topology", "analysis_crs": ANALYSIS_CRS,
        "subbasin_count": len(subbasins), "reach_count": 1, "outlet_id": "S-09-B",
        "station_count": len(station_map), "cycles": "not_assessed_for_source_graph", "disconnected": "not_assessed_for_source_graph",
        "routing_limit": "HydroLite MVP routes total subbasin inflow through one representative outlet reach; source river geometry is audit evidence, not a branch-routing network.",
        "area_difference_percent": area_difference_percent,
        "required_manual_mapping_actions": station_map.loc[station_map["mapping_confidence"].str.startswith("medium"), "station_id"].tolist(),
    }
    _write_json(output / OUTPUTS["topology"], topology)
    return {
        "sources": sources, "source_snapshot": snapshot, "subbasins": subbasins, "reaches": reaches,
        "outlet": outlet.iloc[0].to_dict(), "stations": station_map, "topology": topology,
        "processed": [polygon_copy, line_copy], "geometry": geometry,
    }


def build_real_inputs(source_root: str | Path, workspace_dir: str | Path, output_dir: str | Path, basin: dict[str, Any]) -> dict[str, Any]:
    source = Path(source_root).expanduser().resolve()
    workspace = Path(workspace_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    data_dir = workspace / "standardized" / "m8b"
    cases_dir = workspace / "cases"
    data_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    june = _find_unique(source, "降雨水位流量小时序列_20260622_25.csv")
    may = _find_unique(source, "event_flow_preliminary_calibration.csv")
    may_observed = _find_unique(source, "observed_flow_event_20260525_20260526.csv")
    selected_sources = _required_source_paths(source)
    snapshot = _snapshot_rows(source, selected_sources)
    guard_external_sources(source, snapshot)

    june_data = pd.read_csv(june)
    rainfall = june_data[["time", "rain_mm"]].copy()
    rainfall["time"] = pd.to_datetime(rainfall["time"])
    rainfall["rain_mm"] = pd.to_numeric(rainfall["rain_mm"], errors="raise")
    rainfall_quality_note = "complete interval rainfall"
    missing_rain = rainfall["rain_mm"].isna()
    if missing_rain.any():
        if missing_rain.sum() == 1 and missing_rain.iloc[-1]:
            rainfall = rainfall.loc[~missing_rain].copy()
            rainfall_quality_note = "trailing endpoint without interval rainfall omitted; no rainfall value imputed"
        else:
            raise ValueError("Rainfall contains missing internal interval values; manual review is required")
    if rainfall["time"].duplicated().any() or (rainfall["rain_mm"] < 0).any():
        raise ValueError("Rainfall must contain unique timestamps and non-negative interval values")
    observed = june_data[["time", "flow_m3_s"]].rename(columns={"time": "datetime", "flow_m3_s": "observed_streamflow_m3s"})
    observed["gauge_id"] = "S-09-B"
    rainfall_path = data_dir / "rainfall.csv"
    observed_path = data_dir / "observed_streamflow.csv"
    rainfall.to_csv(rainfall_path, index=False)
    observed[["datetime", "gauge_id", "observed_streamflow_m3s"]].to_csv(observed_path, index=False)

    subcatchments = basin["subbasins"][["subbasin_id", "area_km2"]].rename(columns={"subbasin_id": "id"})
    subcatchments["curve_number"] = 75.0
    subcatchments["lag_hours"] = 6.0
    subcatchments["initial_abstraction_ratio"] = 0.2
    subcatchments_path = data_dir / "subcatchments.csv"
    subcatchments.to_csv(subcatchments_path, index=False)
    reaches = pd.DataFrame([{"id": "R_OUTLET", "from": "BASIN_AGGREGATE", "to": "S-09-B", "K_hours": 2.0, "X": 0.2}])
    reaches_path = data_dir / "reaches.csv"
    reaches.to_csv(reaches_path, index=False)

    parameters = []
    for row in subcatchments.itertuples(index=False):
        for name, value, unit in (("curve_number", row.curve_number, "dimensionless"), ("lag_hours", row.lag_hours, "hours"), ("initial_abstraction_ratio", row.initial_abstraction_ratio, "dimensionless")):
            parameters.append({"element_id": row.id, "parameter": name, "value": value, "unit": unit, "source_type": "default", "source_dataset": "none", "derivation_method": "explicit M8B initial_parameter_estimate", "confidence": "low", "calibrated": False, "warning": "Initial estimate; not calibrated."})
    for name, value, unit in (("K_hours", 2.0, "hours"), ("X", 0.2, "dimensionless")):
        parameters.append({"element_id": "R_OUTLET", "parameter": name, "value": value, "unit": unit, "source_type": "default", "source_dataset": "none", "derivation_method": "explicit stable initial_parameter_estimate", "confidence": "low", "calibrated": False, "warning": "Aggregate outlet routing estimate; not calibrated."})
    parameter_frame = pd.DataFrame(parameters)
    parameter_path = output / OUTPUTS["parameters"]
    _write_excel(parameter_path, {"parameter_provenance": parameter_frame})

    case_path = cases_dir / "gaoqiao_real_event.yaml"
    case = {
        "name": "gaoqiao_real_event", "case_name": "gaoqiao_real_event",
        "time": {"start": str(rainfall["time"].min()), "end": str(rainfall["time"].max()), "dt_minutes": 60},
        "model": {"time_step_hours": 1.0}, "hydrology": {"method": "SCS-CN"},
        "routing": {"channel_method": "Muskingum"},
        "inputs": {"directory": str(data_dir), "rainfall": rainfall_path.name, "subcatchments": subcatchments_path.name, "reaches": reaches_path.name},
        "outputs": {"directory": str(workspace / "outputs" / "gaoqiao_real_event")},
        "observed": {"enabled": True, "observed_streamflow_csv": str(observed_path), "time_column": "datetime", "flow_column": "observed_streamflow_m3s", "gauge_id_column": "gauge_id", "synthetic_demo": False},
        "provenance": {"real_project": True, "rainfall_source": _logical(source, june), "flow_source": _logical(source, june), "flow_source_status": "external_web_observation_derived_table_provenance_requires_confirmation", "basin_definition": "reviewed eight-area GIS derivative", "routing_topology": "aggregate outlet diagnostic"},
        "parameter_provenance": {
            "scenario.model.time_step_hours": {"unit": "hours", "source_type": "derived", "source_reference": "hourly source interval", "confidence": "high", "notes": "Derived from unique hourly timestamps."},
        },
    }
    case_path.write_text(yaml.safe_dump(case, sort_keys=False, allow_unicode=True), encoding="utf-8")
    input_manifest = {
        "schema_version": 1, "real_project": True, "status": "ready_with_warnings",
        "case_logical_path": f"project/cases/{case_path.name}", "analysis_crs": ANALYSIS_CRS,
        "rainfall": {"dataset_id": f"real_{_hash_file(june)[:16]}", "station": "Open-Meteo grid at project outlet", "interval": "1 hour", "unit": "mm/timestep", "timezone": "project local time; source timezone requires confirmation", "coverage": [str(rainfall.time.min()), str(rainfall.time.max())], "quality": f"external gridded forcing; not gauge observation; {rainfall_quality_note}"},
        "flow": {"dataset_id": f"real_{_hash_file(june)[:16]}", "station": "61602500 / S-09-B", "unit": "m3/s", "coverage": [str(observed.datetime.min()), str(observed.datetime.max())], "quality": "derived table; raw web response unavailable"},
        "subbasins": {"count": len(subcatchments), "total_area_km2": float(subcatchments.area_km2.sum())},
        "reaches": {"count": 1, "method": "aggregate representative outlet reach"},
        "external_source_guard": "passed", "source_snapshot": snapshot.to_dict("records"),
        "processed_checksums": {path.name: _hash_file(path) for path in [rainfall_path, observed_path, subcatchments_path, reaches_path, case_path]},
        "warnings": ["CN, lag, K, and X are low-confidence initial estimates.", "Rainfall is gridded external forcing, not a rain-gauge observation.", "Observed-flow raw HTTP response is unavailable.", "Branch river topology is not simulated by the MVP routing engine."],
    }
    _write_json(output / OUTPUTS["input_manifest"], input_manifest)
    return {
        "case": case_path, "data_dir": data_dir, "rainfall": rainfall, "observed": observed,
        "sources": selected_sources, "source_snapshot": snapshot, "parameters": parameter_frame,
        "manifest": input_manifest, "may": may, "may_observed": may_observed,
    }


def build_event_catalog(source_root: str | Path, inputs: dict[str, Any], output_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = Path(source_root).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    june = pd.read_csv(_find_unique(source, "降雨水位流量小时序列_20260622_25.csv"))
    may = pd.read_csv(inputs["may"])
    events = pd.DataFrame([
        {"event_id": MAY_EVENT, "event_start": may["time"].iloc[0], "event_end": may["time"].iloc[-1], "start": may["time"].iloc[0], "end": may["time"].iloc[-1], "rainfall_mm": float(may.rain_mm.sum()), "peak_rainfall_mm_timestep": float(may.rain_mm.max()), "peak_flow_cms": float(may.flow_obs_m3_s.max()), "flow_volume_m3": float(may.flow_obs_m3_s.sum() * 3600), "records": len(may), "data_completeness_percent": float(may[["rain_mm", "flow_obs_m3_s"]].notna().all(axis=1).mean() * 100), "station": "61602500 / S-09-B", "rainfall_provenance": "external report table", "flow_provenance": "external_web_observation_derived_table / provenance_requires_confirmation", "provenance_status": "requires_confirmation", "simulation_provenance_status": "manual_linear_regression_not_hydrolite", "hydrolite_run_id": "", "usable_for_calibration": False, "usable_for_validation": False, "reason": "raw source response missing; retained as diagnostic comparison"},
        {"event_id": MODEL_EVENT, "event_start": june["time"].iloc[0], "event_end": june["time"].iloc[-1], "start": june["time"].iloc[0], "end": june["time"].iloc[-1], "rainfall_mm": float(june.rain_mm.sum()), "peak_rainfall_mm_timestep": float(june.rain_mm.max()), "peak_flow_cms": float(june.flow_m3_s.max()), "flow_volume_m3": float(june.flow_m3_s.sum() * 3600), "records": len(june), "data_completeness_percent": float(june[["rain_mm", "flow_m3_s"]].notna().all(axis=1).mean() * 100), "station": "61602500 / S-09-B", "rainfall_provenance": "Open-Meteo Archive derived table", "flow_provenance": "external_web_observation_derived_table / provenance_requires_confirmation", "provenance_status": "requires_confirmation", "simulation_provenance_status": "actual_hydrolite_run_pending", "hydrolite_run_id": "pending", "usable_for_calibration": False, "usable_for_validation": False, "reason": "actual HydroLite run event; source snapshot lacks raw web response"},
    ])
    gate = assess_event_gate(events)
    readiness = pd.DataFrame([{
        "status": gate["status"], "independent_event_count": gate["independent_event_count"],
        "calibration_events": ",".join(gate["calibration_events"]), "validation_events": ",".join(gate["validation_events"]),
        "test_events": ",".join(gate["test_events"]), "independent_split_status": gate["independent_split_status"],
        "parameter_stability": "insufficient_events", "message": gate["message"],
    }])
    _write_excel(output / OUTPUTS["events"], {"event_catalog": events})
    _write_excel(output / OUTPUTS["readiness"], {"event_readiness": readiness})
    return events, readiness


def assess_event_gate(events: pd.DataFrame) -> dict[str, Any]:
    provenance = events.get("provenance_status", events.get("flow_provenance", pd.Series("", index=events.index))).astype(str)
    confirmed_mask = provenance.str.contains("confirmed", case=False) & ~provenance.str.contains("requires_confirmation|unconfirmed", case=False)
    confirmed = events[confirmed_mask]
    calibration_ok = events.get("usable_for_calibration", pd.Series(True, index=events.index)).fillna(False).astype(bool)
    validation_ok = events.get("usable_for_validation", pd.Series(True, index=events.index)).fillna(False).astype(bool)
    split_role = events.get("split_role", pd.Series("", index=events.index)).fillna("").astype(str).str.casefold()
    explicit_roles = split_role.isin({"calibration", "validation", "test"}).any()
    if explicit_roles:
        calibration_frame = events[confirmed_mask & calibration_ok & split_role.eq("calibration")]
        validation_frame = events[confirmed_mask & validation_ok & split_role.eq("validation")]
        test_frame = events[confirmed_mask & validation_ok & split_role.eq("test")]
    else:
        usable = events[confirmed_mask & (calibration_ok | validation_ok)]
        calibration_frame = usable.iloc[:1]
        validation_frame = usable.iloc[1:2]
        test_frame = usable.iloc[2:3]
    calibration = calibration_frame["event_id"].astype(str).tolist()
    validation = validation_frame["event_id"].astype(str).tolist()
    test = test_frame["event_id"].astype(str).tolist()
    n = len(set(calibration + validation + test))
    simulation_status = events.get("simulation_provenance_status", pd.Series("", index=events.index)).astype(str)
    unknown_simulation = simulation_status.str.contains("unknown", case=False).any()
    required_ids = set(calibration + validation)
    hydrolite_ids = set(events.loc[simulation_status.str.fullmatch("confirmed_hydrolite_run", case=False), "event_id"].astype(str))
    independent_ready = bool(calibration and validation and required_ids <= hydrolite_ids and not unknown_simulation)
    status = "real_data_tested" if independent_ready else "real_data_diagnostic"
    split = "calibration_validation_test_by_complete_event" if independent_ready and test else "calibration_validation_by_complete_event" if independent_ready else "independent_split_not_permitted"
    blockers = []
    if not calibration or not validation: blockers.append("insufficient_independent_events")
    if len(confirmed) < len(events): blockers.append("unconfirmed_event_provenance")
    if unknown_simulation: blockers.append("unknown_simulation_provenance")
    if not independent_ready and calibration and validation and not unknown_simulation: blockers.append("insufficient_confirmed_hydrolite_runs")
    return {
        "status": status, "scientific_status": status, "event_count": len(events),
        "confirmed_event_count": len(confirmed), "independent_event_count": n,
        "independent_validation_ready": independent_ready,
        "hydrolite_model_validated": independent_ready, "blockers": blockers,
        "calibration_events": calibration,
        "validation_events": validation, "test_events": test, "independent_split_status": split,
        "message": "Complete-event calibration and validation split is available." if independent_ready else "Confirmed independent events and HydroLite run provenance are insufficient for independent validation.",
    }


def _canonical_flow_frame(frame: pd.DataFrame, *, observed: bool) -> pd.DataFrame:
    time_column = next((name for name in ("datetime", "timestamp", "time") if name in frame), None)
    flow_columns = ("observed_streamflow_m3s", "flow_obs_m3_s", "flow_m3_s", "flow_cms") if observed else ("simulated_streamflow_m3s", "flow_sim_m3_s", "outflow_cms", "flow_cms")
    flow_column = next((name for name in flow_columns if name in frame), None)
    if not time_column or not flow_column:
        raise ValueError("Flow series requires a timestamp and m3/s flow column")
    target = "observed_streamflow_m3s" if observed else "simulated_streamflow_m3s"
    result = frame[[time_column, flow_column]].rename(columns={time_column: "datetime", flow_column: target}).copy()
    result["datetime"] = pd.to_datetime(result["datetime"], errors="raise")
    result[target] = pd.to_numeric(result[target], errors="raise")
    return result


def _align_flow_series(observed: pd.DataFrame, simulated: pd.DataFrame) -> pd.DataFrame:
    obs = _canonical_flow_frame(observed, observed=True)
    sim = _canonical_flow_frame(simulated, observed=False)
    aligned = obs.merge(sim, on="datetime", how="inner").dropna().sort_values("datetime").reset_index(drop=True)
    if aligned.empty:
        raise ValueError("No aligned observed and simulated flow timestamps")
    return aligned


def calculate_diagnostic_metrics(
    event_id: str,
    observed: pd.DataFrame,
    simulated: pd.DataFrame,
    baseline_name: str = "persistence",
) -> dict[str, Any]:
    aligned = _align_flow_series(observed, simulated)
    obs_values = aligned["observed_streamflow_m3s"]
    sim_values = aligned["simulated_streamflow_m3s"]
    metrics = calculate_all_metrics(obs_values, sim_values)
    obs_peak = int(obs_values.idxmax())
    sim_peak = int(sim_values.idxmax())
    dt_hours = float(aligned["datetime"].diff().dt.total_seconds().dropna().median() / 3600) if len(aligned) > 1 else 1.0
    obs_volume = float(obs_values.sum() * dt_hours * 3600)
    sim_volume = float(sim_values.sum() * dt_hours * 3600)
    observed_peak = float(obs_values.loc[obs_peak])
    simulated_peak = float(sim_values.loc[sim_peak])
    return {
        "event_id": event_id, "baseline_name": baseline_name, "model_id": baseline_name,
        "model_provenance": "actual HydroLite run with recorded inputs/config/git/environment" if baseline_name == "hydrolite_event_model" else "simple transparent benchmark",
        "validation_level": "real_data_diagnostic", "sample_count": int(metrics["n_pairs"]),
        **{key: metrics[key] for key in ("n_pairs", "NSE", "KGE", "RMSE", "MAE", "PBIAS", "R2")},
        "observed_peak_flow_cms": observed_peak, "simulated_peak_flow_cms": simulated_peak,
        "peak_observed_cms": observed_peak, "peak_simulated_cms": simulated_peak,
        "peak_error_cms": simulated_peak - observed_peak,
        "peak_flow_error_percent": (simulated_peak - observed_peak) / observed_peak * 100 if observed_peak else pd.NA,
        "peak_timing_error_hours": float((aligned.loc[sim_peak, "datetime"] - aligned.loc[obs_peak, "datetime"]).total_seconds() / 3600),
        "observed_volume_m3": obs_volume, "simulated_volume_m3": sim_volume,
        "volume_error_percent": (sim_volume - obs_volume) / obs_volume * 100 if obs_volume else pd.NA,
    }


def build_scenario_comparison(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("At least one scenario is required")
    if "scenario_type" not in frame:
        frame["scenario_type"] = "what_if_sensitivity_scenario"
    if set(frame["scenario_type"]) != {"what_if_sensitivity_scenario"}:
        raise ValueError("Scenarios must be explicitly labeled what_if_sensitivity_scenario")
    baseline_rows = frame.loc[np.isclose(frame["rainfall_scale"], 1.0)] if "rainfall_scale" in frame else frame.loc[frame["scenario_id"].eq("baseline")]
    if len(baseline_rows) != 1:
        raise ValueError("Scenario comparison requires exactly one explicit baseline or rainfall_scale=1.0")
    baseline = baseline_rows.iloc[0]
    frame["peak_flow_change_cms"] = frame["peak_flow_cms"] - float(baseline["peak_flow_cms"])
    frame["peak_flow_change_percent"] = np.where(float(baseline["peak_flow_cms"]), frame["peak_flow_change_cms"] / float(baseline["peak_flow_cms"]) * 100, pd.NA)
    if "runoff_volume_m3" in frame:
        frame["runoff_volume_change_m3"] = frame["runoff_volume_m3"] - float(baseline["runoff_volume_m3"])
        frame["runoff_volume_change_percent"] = np.where(float(baseline["runoff_volume_m3"]), frame["runoff_volume_change_m3"] / float(baseline["runoff_volume_m3"]) * 100, pd.NA)
    return frame


def _prepare_scenarios(inputs: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    base_case = yaml.safe_load(inputs["case"].read_text(encoding="utf-8"))
    prepared = []
    scenario_dir = workspace / "standardized" / "m8b" / "scenarios"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    for factor in SCENARIO_FACTORS:
        scenario_id = f"rainfall_scale_{str(factor).replace('.', '_')}"
        rain = inputs["rainfall"].copy()
        rain["rain_mm"] *= factor
        rain_path = scenario_dir / f"{scenario_id}.csv"
        rain.to_csv(rain_path, index=False)
        case = json.loads(json.dumps(base_case, default=str))
        case["name"] = f"gaoqiao_{scenario_id}"
        case["case_name"] = case["name"]
        case["inputs"]["directory"] = str(scenario_dir)
        case["inputs"]["rainfall"] = rain_path.name
        case["inputs"]["subcatchments"] = str(Path(inputs["model_input_dir"]) / "subbasins.csv")
        case["inputs"]["reaches"] = str(Path(inputs["model_input_dir"]) / "reaches.csv")
        case["outputs"]["directory"] = str(workspace / "outputs" / "scenarios" / scenario_id)
        case["observed"] = {"enabled": False}
        case["scenario"] = {"scenario_id": scenario_id, "scenario_type": "what_if_sensitivity_scenario", "rainfall_scale": factor, "not_probability_forecast": True}
        case_path = workspace / "cases" / f"{scenario_id}.yaml"
        case_path.write_text(yaml.safe_dump(case, sort_keys=False, allow_unicode=True), encoding="utf-8")
        prepared.append({"scenario_id": scenario_id, "factor": factor, "rainfall": rain, "rainfall_path": rain_path, "case_path": case_path})
    return prepared


def _run_scenarios(inputs: dict[str, Any], workspace: Path, output: Path, prepared: list[dict[str, Any]] | None = None) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows, manifests = [], []
    for item in prepared or _prepare_scenarios(inputs, workspace):
        scenario_id, factor, rain, case_path = item["scenario_id"], item["factor"], item["rainfall"], item["case_path"]
        run = run_case(case_path)
        result = pd.read_csv(run.result_flow_csv)
        rows.append({
            "scenario_id": scenario_id, "scenario_type": "what_if_sensitivity_scenario", "rainfall_scale": factor,
            "forcing_definition": f"reviewed event interval rainfall multiplied by {factor:g}", "total_rainfall_mm": float(rain.rain_mm.sum()),
            "peak_flow_cms": float(result.outflow_cms.max()), "peak_time": str(result.loc[result.outflow_cms.idxmax(), "time"]),
            "runoff_volume_m3": float(result.outflow_cms.sum() * 3600), "routing_response": "one aggregate Muskingum outlet reach",
            "forcing_uncertainty": "Open-Meteo forcing is not a local gauge observation", "parameter_uncertainty": "initial uncalibrated CN/lag/K/X",
            "data_uncertainty": "raw station web response unavailable", "structural_uncertainty": "event model excludes baseflow and branch routing",
        })
        manifests.append({
            "scenario_id": scenario_id, "case": f"project/cases/{case_path.name}",
            "result_checksum": _hash_file(run.result_flow_csv),
            "artifacts": {
                path.name: {"path": f"project/outputs/scenarios/{scenario_id}/{path.name}", "checksum": _hash_file(path)}
                for path in run.output_dir.iterdir() if path.is_file()
            },
        })
    comparison = build_scenario_comparison(rows)
    _write_excel(output / OUTPUTS["scenarios"], {"scenario_comparison": comparison})
    return comparison, manifests


def _add_reach_balance(path: Path, result: pd.DataFrame, reaches: pd.DataFrame, dt_hours: float) -> pd.DataFrame:
    subbasin = pd.read_excel(path, sheet_name="subbasin_balance")
    outlet = pd.read_excel(path, sheet_name="outlet_balance")
    rows = []
    inflow = result["inflow_cms"]
    for reach in reaches.itertuples(index=False):
        outflow = result[f"reach_{reach.id}_outflow_cms"]
        inflow_volume = float(inflow.sum() * dt_hours * 3600)
        outflow_volume = float(outflow.sum() * dt_hours * 3600)
        error = outflow_volume - inflow_volume
        rows.append({
            "reach_id": str(reach.id), "inflow_volume_m3": inflow_volume,
            "outflow_volume_m3": outflow_volume, "balance_error_m3": error,
            "balance_error_percent": error / inflow_volume * 100 if inflow_volume else 0.0,
        })
        inflow = outflow
    reach_balance = pd.DataFrame(rows)
    _write_excel(path, {"subbasin_balance": subbasin, "reach_balance": reach_balance, "outlet_balance": outlet})
    return reach_balance


def _water_quality_outputs(source: Path, output: Path) -> dict[str, Any]:
    concentration_path = _find_unique(source, "20260623_24水样检测结果规范化.csv")
    load_path = _find_unique(source, "20260623_24雨天补充采样瞬时通量.csv")
    stage_path = _find_unique(source, "降雨水位流量小时序列_20260622_25.csv")
    concentrations = pd.read_csv(concentration_path)
    loads = pd.read_csv(load_path)
    stages = pd.read_csv(stage_path)
    stages["time"] = pd.to_datetime(stages["time"])
    peak_index = int(stages["flow_m3_s"].idxmax())
    stages["hydrologic_phase"] = "rising_limb"
    stages.loc[stages.index > peak_index + 1, "hydrologic_phase"] = "recession"
    stages.loc[(stages.index >= peak_index - 1) & (stages.index <= peak_index + 1), "hydrologic_phase"] = "peak"
    stages["phase_basis"] = "hourly observed-flow-derived table; no confirmed pre-event sample"
    event = concentrations.merge(loads, on=["序号", "点位编号", "片区", "点位类型"], how="left")
    event["analysis_type"] = "wet_weather_observational_diagnostic"
    event["process_model_claim"] = False
    event["source_apportionment_available"] = False
    _write_excel(output / OUTPUTS["wet_weather"], {"station_observations": event, "event_timeline": stages})
    load_columns = [column for column in loads if column.endswith("_t_d")]
    load_diag = loads[["序号", "点位编号", "片区", "点位类型", "估算流量_m3_s", *load_columns, "流量估算置信度"]].copy()
    load_diag["load_type"] = "instantaneous_estimated_flow_assisted_diagnostic"
    load_diag["observed_flow_load"] = False
    load_diag["modeled_flow_assisted_load"] = False
    load_diag["continuous_load_available"] = False
    load_diag["event_total_load_available"] = False
    load_diag["limitation"] = "Instantaneous estimated discharge is not a continuous observed-flow record or event total load."
    _write_excel(output / OUTPUTS["loads"], {"instantaneous_load_diagnostic": load_diag})
    return {"station_count": int(event["点位编号"].nunique()), "pollutants": ["CODMn", "NH3-N", "TN", "TP"], "observed_flow_load": "unavailable", "modeled_flow_assisted_load": "unavailable", "continuous_load": "unavailable", "event_total_load": "unavailable", "sources": [concentration_path, load_path, stage_path]}


def _validation_outputs(inputs: dict[str, Any], run_output: Any, events: pd.DataFrame, output: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    observed = inputs["observed"].copy()
    result = pd.read_csv(run_output.result_flow_csv)
    result = result.rename(columns={"time": "datetime", "outflow_cms": "simulated_streamflow_m3s"})
    aligned = _align_flow_series(observed, result)
    hydrolite_row = calculate_diagnostic_metrics(MODEL_EVENT, observed, result, baseline_name="hydrolite_event_model")
    persistence = pd.DataFrame({
        "datetime": aligned["datetime"],
        "simulated_streamflow_m3s": np.full(len(aligned), float(aligned["observed_streamflow_m3s"].iloc[0])),
    })
    baseline_row = calculate_diagnostic_metrics(MODEL_EVENT, observed, persistence, baseline_name="persistence")
    metrics = pd.DataFrame([hydrolite_row, baseline_row])
    aligned["baseline_flow_cms"] = persistence["simulated_streamflow_m3s"]
    june_hydro = metrics.loc[metrics.model_id.eq("hydrolite_event_model")].iloc[0]
    baseline = metrics.loc[metrics.model_id.eq("persistence")].iloc[0]
    existing = pd.read_csv(inputs["may"])
    existing_row = calculate_diagnostic_metrics(
        MAY_EVENT,
        existing[["time", "flow_obs_m3_s"]],
        existing[["time", "flow_sim_m3_s"]],
        baseline_name="existing_linear_rainfall_response",
    )
    existing_row.update({
        "model_provenance": "manual linear regression found in build_full_source_report.py; not HydroLite, SWAT, or HEC-HMS",
        "validation_level": "provenance_resolved_not_hydrolite",
    })
    metrics = pd.concat([metrics, pd.DataFrame([existing_row])], ignore_index=True)
    gate = assess_event_gate(events)
    summary = pd.DataFrame([{
        "scientific_status": gate["status"], "actual_hydrolite_run": True,
        "independent_validation": False, "calibration_performed": False,
        "calibration_reason": "No confirmed independent event set; source flow provenance requires confirmation.",
        "parameter_stability": "insufficient_events", "worst_event": MODEL_EVENT,
        "hydrolite_NSE": june_hydro.NSE, "hydrolite_KGE": june_hydro.KGE,
        "baseline_NSE": baseline.NSE, "baseline_KGE": baseline.KGE,
        "water_balance_gate": "see actual run water_balance.xlsx",
    }])
    _write_excel(output / OUTPUTS["metrics"], {"event_metrics": metrics})
    _write_excel(output / OUTPUTS["validation"], {"validation_summary": summary})
    aligned.to_csv(output / OUTPUTS["aligned"], index=False)
    return metrics, summary, aligned


def _friction_closure(output: Path) -> pd.DataFrame:
    rows = [
        ("FR-003", "external references", "partially_fixed", "Checksum/mtime guard added; UI reference picker remains."),
        ("FR-004", "critical Chinese field mapping", "partially_fixed", "Required hydrology/WQ fields mapped; remaining catalogue fields still need review."),
        ("FR-005", "invalid river geometry", "fixed", "Processed copy omits one unreadable feature and records lineage; raw remains unchanged."),
        ("FR-006", "model provenance", "fixed", "41-point simulation resolved as manual linear regression and cannot be attributed to HydroLite."),
        ("FR-007", "flow/load evidence", "deferred_to_M9", "Only instantaneous estimated-flow diagnostics are retained."),
        ("FR-008", "HydroLite input conversion", "fixed", "Reviewed eight-area input and actual HydroLite case generated."),
        ("FR-009", "delivery operator effort", "partially_fixed", "M8B orchestration creates a reviewed deliverable; UI action remains future work."),
        ("FR-010", "GEE authentication", "open", "Unrelated optional dependency; not changed in M8B."),
    ]
    frame = pd.DataFrame(rows, columns=["friction_id", "area", "closure_status", "evidence"])
    _write_excel(output / OUTPUTS["friction"], {"friction_closure": frame})
    return frame


def _write_reports(output: Path, facts: dict[str, Any]) -> None:
    metric = facts["hydrolite_metric"]
    scenarios = facts["scenarios"]
    scenario_lines = "\n".join(f"- `{row.scenario_id}`: rainfall {row.total_rainfall_mm:.1f} mm, peak {row.peak_flow_cms:.3f} m3/s, volume {row.runoff_volume_m3:.0f} m3." for row in scenarios.itertuples())
    zh = f"""# M8B 高桥河真实 HydroLite 模型闭环报告

## 1. 项目与版本
- Project Version 2: `{facts['version']['project_version_id']}`
- Parent Version: `{facts['version']['parent_version_id']}`
- Actual Run: `{facts['run']['run_id']}`

## 2. 数据、流域与拓扑
- 实际八分区面积 {facts['area_km2']:.3f} km2，分析 CRS `{ANALYSIS_CRS}`。
    - 源 GIS 仅读；河道 {facts['line_before']} 条中 {facts['line_omitted']} 条不可读几何仅在 processed copy 中省略。
- HydroLite MVP 以 8 个子流域汇入代表性出口河段，不声称分汊河网路由。

## 3. 输入、参数与真实运行
    - {facts['rain_start']}至{facts['rain_end']}小时降雨 {facts['rainfall_mm']:.1f} mm，来源为 Open-Meteo 网格派生表，非雨量站观测。
- CN=75、lag=6 h、K=2 h、X=0.2 均为低置信度初始参数，未率定。
- 实际执行模块 `hydrolite.runner.run_case`，结果和水量平衡均由当前代码生成。

## 4. 率定与评价
- 两个短事件均缺少原始网站响应快照，不执行率定或独立验证。
- 科学状态：`real_data_diagnostic`。
- 诊断事件 NSE={metric['NSE']:.4f}, KGE={metric['KGE']:.4f}, RMSE={metric['RMSE']:.3f} m3/s, MAE={metric['MAE']:.3f} m3/s, PBIAS={metric['PBIAS']:.2f}%, R2={metric['R2']:.4f}。
- 非零基流和分汊河网未表征，指标仅用于诊断。
    - 原 41 点模拟已追溯为手工线性降雨滞后回归，不是 HydroLite、SWAT 或 HEC-HMS 结果。
    - `continuous_hydrology={facts['continuous_status']}`；Gamma/Graph 未使用本项目数据做价值验证；`water_quality_method_lab={facts['wq_lab_status']}`。

## 5. What-if 水文情景
{scenario_lines}

上述仅为降雨倍率敏感性情景，不是概率预报或重现期洪水。

## 6. 湿天水质观测诊断
- {facts['wq']['station_count']} 个点位，指标 CODMn/NH3-N/TN/TP。
- 仅展示湿天观测与估算瞬时通量；无连续观测负荷、事件总负荷或污染源归因。
- `water_quality` 主能力仍为 `planned`。

## 7. 产品、交付与 M9 门禁
- Scientific Validation: `real_data_diagnostic`
- Delivery Review: `reviewed`
- Water Environment Hydrology Gate: `{facts['gate']}`
- 仍需获得原始观测快照、实测雨量、基流/初始状态、可验证河网拓扑与至少三场独立事件。

本节点没有实施 M9 水质过程模型。
"""
    en = f"""# M8B Gaoqiao Real HydroLite Model Closure

## Project and governed run
Project Version 2 `{facts['version']['project_version_id']}` descends from `{facts['version']['parent_version_id']}`. Actual run `{facts['run']['run_id']}` executed `hydrolite.runner.run_case` using a reviewed eight-area derivative and one representative aggregate outlet reach.

## Evidence and scientific status
The {facts['rain_start']}--{facts['rain_end']} forcing totals {facts['rainfall_mm']:.1f} mm and is an Open-Meteo-derived grid series rather than a rain-gauge observation. Flow is a derived station table whose original web response is not retained. CN, lag, K, and X are uncalibrated low-confidence initial estimates. Therefore the result is `real_data_diagnostic`, not independent validation.

Diagnostic metrics are NSE={metric['NSE']:.4f}, KGE={metric['KGE']:.4f}, RMSE={metric['RMSE']:.3f} m3/s, MAE={metric['MAE']:.3f} m3/s, PBIAS={metric['PBIAS']:.2f}%, and R2={metric['R2']:.4f}. Non-zero baseflow and branch routing are not represented. The former 41-point simulation was traced to a manual linear lag regression and is not a HydroLite, SWAT, or HEC-HMS result.

## Scenarios and water quality
Four rainfall multipliers (0.8, 1.0, 1.2, 1.5) are explicitly labeled what-if sensitivity scenarios, not probability forecasts or return periods. Wet-weather CODMn, NH3-N, TN, and TP results are observational diagnostics only; continuous and event-total loads remain unavailable. The main `water_quality` capability remains `planned`.

## Delivery gate
Scientific status is `real_data_diagnostic`; delivery review is `reviewed`; the water-environment hydrology gate is `{facts['gate']}`. Original observation snapshots, gauge rainfall, initial/baseflow states, confirmed topology, and at least three independent events remain gaps. M9 is not implemented here.
"""
    (output / OUTPUTS["report_zh"]).parent.mkdir(parents=True, exist_ok=True)
    (output / OUTPUTS["report_zh"]).write_text(zh, encoding="utf-8")
    (output / OUTPUTS["report_en"]).write_text(en, encoding="utf-8")


def run_real_project_model_validation(
    source_root: str | Path, *, workspace_dir: str | Path,
    baseline_output_dir: str | Path = "output/real_project_validation",
) -> dict[str, Any]:
    started = perf_counter()
    source = Path(source_root).expanduser().resolve()
    workspace = Path(workspace_dir).expanduser().resolve()
    baseline = Path(baseline_output_dir).expanduser().resolve()
    output = baseline / "m8b"
    if not (workspace / "project.yaml").is_file() or not (baseline / "reports/m8a_real_project_manifest.json").is_file():
        raise FileNotFoundError("M8A workspace and baseline outputs are required before M8B")
    m8a_manifest = json.loads((baseline / "reports/m8a_real_project_manifest.json").read_text(encoding="utf-8"))
    project = resolve_project("gaoqiao_river_basin_real_validation")
    if Path(project["workspace_path"]).resolve() != workspace:
        raise RuntimeError("M8B workspace does not match the registered M8A project workspace")
    if m8a_manifest.get("project_id") != project["project_id"] or m8a_manifest.get("project_version") != "pv_ecc7f20b592e":
        raise RuntimeError("M8A project or Version 1 baseline does not match the required M8B parent")
    for name in ("cases", "configs", "data", "output", "reports"):
        (workspace / name).mkdir(exist_ok=True)

    m8a_inventory = pd.read_excel(baseline / "inventory/real_project_data_inventory.xlsx")
    source_guard = guard_external_sources(source, m8a_inventory, _required_source_paths(source))
    basin = build_basin_definition(source, workspace, output)
    inputs = build_real_inputs(source, workspace, output, basin)
    events, readiness = build_event_catalog(source, inputs, output)
    _register_processed_inputs(workspace, inputs, basin)
    _apply_input_builder(workspace, inputs, output)
    prepared_scenarios = _prepare_scenarios(inputs, workspace)

    versions_before = sorted(list_project_version_records(project_id="gaoqiao_river_basin_real_validation"), key=lambda row: int(row["version_number"]))
    if not versions_before:
        raise RuntimeError("Project Version 1 is missing")
    existing_m8b = [row for row in versions_before if row.get("status") == "real_project_model_validation"]
    if existing_m8b:
        version = existing_m8b[-1]
    else:
        if int(versions_before[-1]["version_number"]) != 1:
            raise RuntimeError("M8B requires Project Version 1 as its parent")
        version = create_project_version(
            "gaoqiao_river_basin_real_validation", created_by="m8b_model_validation",
            description="Reviewed real basin inputs, actual HydroLite run, diagnostic validation, and what-if scenarios",
            scenario_ids=("gaoqiao_real_event", *[f"rainfall_scale_{str(value).replace('.', '_')}" for value in SCENARIO_FACTORS]),
            snapshot_mode="referenced", status="real_project_model_validation",
        )
    if int(version["version_number"]) != 2 or version["parent_version_id"] != versions_before[0]["project_version_id"]:
        raise RuntimeError("Project Version 2 parent chain is invalid")

    actual_started = _now()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run_paths = ensure_runtime_directories(run_id)
    run_config = run_paths["configuration"] / "m8b_actual_run_config.json"
    run_config.write_text(json.dumps({
        "case": f"project/cases/{inputs['case'].name}", "case_checksum": _hash_file(inputs["case"]),
        "actual_module": "hydrolite.runner.run_case", "project_version_id": version["project_version_id"],
        "model_modules": ["SCS-CN", "triangular unit hydrograph", "Muskingum"],
        "parameter_provenance": inputs["parameters"].to_dict("records"),
        "external_source_guard": source_guard["status"],
    }, indent=2), encoding="utf-8")
    environment = capture_delivery_environment(version["project_version_id"])
    run = create_run_record(
        run_id=run_id, project_id="gaoqiao_river_basin_real_validation", project_version_id=version["project_version_id"],
        data_snapshot_id=version["data_snapshot_id"], configuration_snapshot_id=version["configuration_snapshot_id"],
        workflow_id="real_project_model_validation", run_name="M8B actual HydroLite real-project event run", run_mode="local",
        requested_at=actual_started, started_at=actual_started, finished_at=None, status="running", progress=10,
        current_stage="hydrology", configuration_path=str(run_config), configuration_checksum=_hash_file(run_config),
        git_commit=_git_commit(), hydrolite_version=__version__, python_version=sys.version.split()[0],
        environment_id=environment["environment_id"], result_status="", error_summary="", legacy_unversioned=False,
        warnings=["Observed-flow provenance requires confirmation", "Initial uncalibrated parameters", "Aggregate outlet topology", "Single-event HydroLite diagnostic"],
    )
    try:
        run_output = run_case(inputs["case"])
    except Exception as exc:
        update_run_record(run_id, status="failed", progress=100, finished_at=_now(), result_status="failed", error_summary=f"{type(exc).__name__}: {exc}")
        raise
    actual_finished = _now()
    result_flow = pd.read_csv(run_output.result_flow_csv)
    model_reaches = pd.read_csv(Path(inputs["model_input_dir"]) / "reaches.csv")
    reach_balance = _add_reach_balance(run_output.water_balance_xlsx, result_flow, model_reaches, 1.0)
    subbasin_balance = pd.read_excel(run_output.water_balance_xlsx, sheet_name="subbasin_balance")
    water_balance = pd.read_excel(run_output.water_balance_xlsx, sheet_name="outlet_balance")
    balance_error = float(water_balance.iloc[0]["balance_error_percent"])
    max_balance_error = max(
        float(subbasin_balance["balance_error_percent"].abs().max()),
        float(reach_balance["balance_error_percent"].abs().max()),
        abs(balance_error),
    )
    water_balance_status = "passed" if max_balance_error <= 5 else "failed"
    if water_balance_status != "passed":
        update_run_record(run_id, status="failed", progress=100, finished_at=actual_finished, result_status="failed", error_summary=f"Water balance error {max_balance_error}%")
        raise RuntimeError(f"Actual HydroLite run failed water balance gate: {max_balance_error}%")
    run = update_run_record(run_id, status="succeeded", progress=100, finished_at=actual_finished, current_stage="reporting", result_status="real_data_diagnostic", error_summary="")
    events.loc[events.event_id.eq(MODEL_EVENT), ["simulation_provenance_status", "hydrolite_run_id"]] = ["confirmed_hydrolite_run", run_id]
    updated_event_gate = assess_event_gate(events)
    readiness.loc[:, "status"] = updated_event_gate["status"]
    readiness["actual_hydrolite_run_id"] = run_id
    readiness["hydrolite_simulation_provenance"] = "confirmed_hydrolite_run"
    readiness["blockers"] = ",".join(updated_event_gate["blockers"])
    _write_excel(output / OUTPUTS["events"], {"event_catalog": events})
    _write_excel(output / OUTPUTS["readiness"], {"event_readiness": readiness})

    metrics, validation, aligned = _validation_outputs(inputs, run_output, events, output)
    scenarios, scenario_manifests = _run_scenarios(inputs, workspace, output, prepared_scenarios)
    wq = _water_quality_outputs(source, output)
    friction = _friction_closure(output)
    gate_checks = pd.DataFrame([
        {"check": "real_basin", "status": "passed", "severity": "fatal", "message": "Reviewed eight-area derivative exists."},
        {"check": "actual_hydrolite_run", "status": "passed", "severity": "fatal", "message": run_id},
        {"check": "water_balance", "status": water_balance_status, "severity": "fatal", "message": f"maximum absolute error {max_balance_error:.6g}%"},
        {"check": "observed_comparison", "status": "passed" if len(aligned) else "failed", "severity": "fatal", "message": f"{len(aligned)} aligned records"},
        {"check": "flow_provenance", "status": "warning", "severity": "warning", "message": "Derived observation table retained; raw web response unavailable."},
        {"check": "parameter_evidence", "status": "warning", "severity": "warning", "message": "CN/lag/K/X are uncalibrated initial estimates."},
        {"check": "source_branch_topology", "status": "warning", "severity": "warning", "message": "Aggregate outlet topology only."},
        {"check": "independent_events", "status": "warning", "severity": "warning", "message": "Independent calibration/validation is unavailable."},
    ])
    gate = "blocked" if ((gate_checks.severity == "fatal") & (gate_checks.status != "passed")).any() else "ready_with_warnings"
    _write_excel(output / OUTPUTS["validation"], {"validation_summary": validation, "water_environment_gate": gate_checks})
    version_diff = compare_project_versions(version["parent_version_id"], version["project_version_id"])
    _write_excel(output / OUTPUTS["versions"], {
        "version_summary": pd.DataFrame([{"from_version": version["parent_version_id"], "to_version": version["project_version_id"], "parent_linked": True, "data_changed": True, "mapping_changed": True, "config_changed": True, "actual_run_added": run_id, "validation_status": "real_data_diagnostic", "scenario_outputs_added": len(scenarios)}]),
        "version_diff": pd.DataFrame([{"field": key, **value} for key, value in version_diff["changes"].items()]),
    })

    hydrolite_metric = metrics.loc[metrics.model_id.eq("hydrolite_event_model")].iloc[0].to_dict()
    line_geometry = basin["geometry"].loc[basin["geometry"].dataset.eq("reviewed_river_lines")].iloc[0]
    facts = {
        "version": version, "run": run, "area_km2": float(basin["subbasins"].area_km2.sum()),
        "hydrolite_metric": hydrolite_metric, "scenarios": scenarios, "wq": wq, "gate": gate,
        "rainfall_mm": float(inputs["rainfall"].rain_mm.sum()),
        "rain_start": str(inputs["rainfall"].time.min()), "rain_end": str(inputs["rainfall"].time.max()),
        "line_before": int(line_geometry.before_count), "line_omitted": int(line_geometry.before_count - line_geometry.after_count),
        "continuous_status": get_capability("continuous_hydrology")["status"],
        "wq_lab_status": get_capability("water_quality_method_lab")["status"],
    }
    _write_reports(output, facts)

    run_manifest = {
        "run_id": run_id, "run_status": "succeeded", "scientific_status": "real_data_diagnostic",
        "project_version": version["project_version_id"], "git_commit": _git_commit(), "hydrolite_version": __version__,
        "python_version": sys.version.split()[0], "os": platform.platform(), "actual_module": "hydrolite.runner.run_case",
        "model_modules": ["SCS-CN", "triangular unit hydrograph", "Muskingum"],
        "case_logical_path": f"project/cases/{inputs['case'].name}", "data_snapshot_id": version["data_snapshot_id"],
        "configuration_snapshot_id": version["configuration_snapshot_id"], "started_at": actual_started, "finished_at": actual_finished,
        "parameters": inputs["parameters"].to_dict("records"), "water_balance_status": water_balance_status,
        "outlet_balance_error_percent": balance_error, "max_balance_error_percent": max_balance_error,
        "artifacts": {path.name: _hash_file(path) for path in run_output.output_dir.iterdir() if path.is_file()},
    }
    _write_json(output / OUTPUTS["run_manifest"], run_manifest)

    manifest = {
        "schema_version": 1, "real_project": True, "project_id": "gaoqiao_river_basin_real_validation",
        "project_version": version["project_version_id"], "project_version_number": version["version_number"], "parent_version": version["parent_version_id"],
        "data_snapshot_id": version["data_snapshot_id"], "configuration_snapshot_id": version["configuration_snapshot_id"],
        "actual_hydrolite_run_ids": [run_id], "actual_hydrolite_module": "hydrolite.runner.run_case", "git_commit": _git_commit(),
        "model_modules": run_manifest["model_modules"], "dataset_ids": inputs["source_snapshot"]["dataset_id"].tolist(),
        "checksums": dict(zip(inputs["source_snapshot"]["dataset_id"], inputs["source_snapshot"]["checksum"])),
        "parameter_provenance": inputs["parameters"].to_dict("records"), "calibration_events": [], "validation_events": [],
        "events_assessed": events.event_id.tolist(), "scientific_status": "real_data_diagnostic",
        "scenario_type": "what_if_sensitivity_scenario", "scenario_ids": scenarios.scenario_id.tolist(),
        "water_environment_hydrology_gate": gate, "water_environment_hydrology_gate_checks": gate_checks.to_dict("records"),
        "water_quality_main_status": get_capability("water_quality")["status"],
        "deliverable_id": "pending", "delivery_review_status": "pending", "integrity_status": "pending",
        "warnings": ["Observation provenance requires confirmation.", "Only one actual HydroLite event run is evaluated.", "CN, lag, K, and X are uncalibrated initial estimates.", "Rainfall scenarios are what-if sensitivities, not probability forecasts."],
        "limitations": ["No independent hydrologic validation.", "No baseflow or branched river routing.", "No water-quality process simulation or source apportionment."],
        "scenario_runs": scenario_manifests, "duration_seconds": round(perf_counter() - started, 3), "timestamp": _now(),
    }
    manifest_path = _write_json(output / OUTPUTS["manifest"], manifest)
    artifact_paths = [output / relative for relative in OUTPUTS.values() if (output / relative).is_file()]
    artifact_paths.extend(path for path in run_output.output_dir.iterdir() if path.is_file())
    artifact_paths.extend(
        path
        for item in prepared_scenarios
        for path in (workspace / "outputs" / "scenarios" / item["scenario_id"]).iterdir()
        if path.is_file()
    )
    artifacts = [register_artifact(run_id, None, path) for path in dict.fromkeys(artifact_paths)]
    report_names = {Path(OUTPUTS["report_zh"]).name, Path(OUTPUTS["report_en"]).name}
    report_ids = [item["artifact_id"] for item in artifacts if item["display_name"] in report_names]
    artifact_ids = [item["artifact_id"] for item in artifacts if item["artifact_id"] not in report_ids]
    deliverable = create_deliverable(
        version["project_version_id"], run_ids=[run_id], artifact_ids=artifact_ids, report_ids=report_ids,
        created_by="m8b_model_validation", scientific_validation_level="real_data_diagnostic",
        capabilities=["hydrology", "water_quality_data_analysis"],
        warnings=["INSUFFICIENT_MULTI_EVENT_REAL_DATA", "OBSERVATION_PROVENANCE_REQUIRES_CONFIRMATION", "INITIAL_PARAMETERS_NOT_CALIBRATED"],
        limitations=["Hydrology is a real-project single-event diagnostic, not independent validation.", "Rainfall is gridded forcing and observed-flow raw response is unavailable.", "Aggregate outlet routing excludes branch topology and baseflow.", "Water-quality output is observational analysis, not process simulation."],
        delivery_claim="analysis_report",
    )
    manifest.update({"deliverable_id": deliverable["deliverable_id"], "delivery_review_status": "draft", "integrity_status": "pending"})
    _write_json(manifest_path, manifest)
    register_artifact(run_id, None, manifest_path)
    submit_delivery(deliverable["deliverable_id"], actor="m8b_analyst", comment="Submitted as a real-project HydroLite diagnostic with explicit evidence limitations.")
    deliverable = review_delivery(deliverable["deliverable_id"], actor="m8b_reviewer", comment="Reviewed for run provenance, balance, event gate, scenarios, and water-quality interpretation; not approved for delivery.")
    integrity = verify_deliverable(deliverable["deliverable_id"])
    manifest.update({"delivery_review_status": deliverable["review_status"], "integrity_status": integrity["status"], "duration_seconds": round(perf_counter() - started, 3), "timestamp": _now()})
    _write_json(manifest_path, manifest)
    register_artifact(run_id, None, manifest_path)
    write_deliverable_manifest(deliverable["deliverable_id"])
    integrity = verify_deliverable(deliverable["deliverable_id"])
    if integrity["status"] != "passed":
        raise RuntimeError(f"M8B deliverable integrity failed: {integrity}")
    pointer = workspace / "reports" / "real_project_baseline_pointer.json"
    pointer.write_text(json.dumps({"output_dir": str(baseline)}, indent=2) + "\n", encoding="utf-8")
    return {"status": "passed", "output_dir": output, "case": inputs["case"], "version": version, "run": run, "deliverable": deliverable, "integrity": integrity, "manifest": manifest_path, "metrics": metrics, "scenarios": scenarios, "events": events, "friction": friction, "water_quality": wq, "gate": gate}
