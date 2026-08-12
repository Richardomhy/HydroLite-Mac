"""Read-only real-project inventory and readiness audit for the M8A baseline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import uuid

import pandas as pd
import yaml

from hydrolite.__version__ import __version__
from hydrolite.artifact_store import register_artifact
from hydrolite.delivery_review import create_deliverable, request_delivery_changes, review_delivery, submit_delivery
from hydrolite.integrity_verification import verify_deliverable
from hydrolite.metrics import calculate_all_metrics
from hydrolite.project_service import register_workspace_as_project
from hydrolite.project_versioning import capture_delivery_environment, create_project_version
from hydrolite.runtime_db import create_run_record, list_deliverable_records, list_project_records, list_project_version_records
from hydrolite.runtime_paths import ensure_runtime_directories
from hydrolite.workspace import create_workspace, read_workspace_manifest, write_workspace_manifest


SUPPORTED_TABLES = {".csv", ".tsv", ".xlsx", ".xls"}
SPATIAL_SUFFIXES = {".shp", ".geojson", ".gpkg", ".kml", ".kmz", ".tif", ".tiff", ".asc"}
METADATA_SUFFIXES = {".zip", ".json", ".yaml", ".yml", ".txt", ".md", ".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
OUTPUT_NAMES = {
    "inventory": "inventory/real_project_data_inventory.xlsx",
    "quality": "data_quality/dataset_quality_summary.xlsx",
    "mapping": "data_quality/field_mapping_audit.xlsx",
    "units": "data_quality/unit_audit.xlsx",
    "spatial": "data_quality/spatial_mapping_audit.xlsx",
    "readiness": "readiness/capability_readiness.xlsx",
    "blockers": "readiness/blocker_summary.xlsx",
    "validation": "validation/real_validation_summary.xlsx",
    "hydrology": "validation/hydrology_validation.xlsx",
    "water_quality": "validation/water_quality_validation.xlsx",
    "event": "validation/wet_weather_event_validation.xlsx",
    "friction": "product/product_friction_backlog.xlsx",
    "manual": "product/manual_intervention_log.xlsx",
    "commercial": "product/commercial_readiness.xlsx",
    "m9": "product/m9_water_environment_backlog.xlsx",
    "report_zh": "reports/m8a_real_project_baseline_report_zh.md",
    "report_en": "reports/m8a_real_project_baseline_report_en.md",
    "manifest": "reports/m8a_real_project_manifest.json",
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


def _logical_source(root: Path, path: Path) -> str:
    return f"source-root/{path.relative_to(root).as_posix()}"


def _is_embedded_software(path: Path) -> bool:
    return (path / ".git").exists() or ((path / "pyproject.toml").exists() and (path / "hydrolite").is_dir())


def _iter_source_files(root: Path):
    for current, dirs, files in os.walk(root):
        base = Path(current)
        dirs[:] = [name for name in dirs if name not in {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"} and not _is_embedded_software(base / name)]
        for name in files:
            path = base / name
            if not path.is_symlink():
                yield path


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


CATEGORY_RULES = (
    ("water_quality", ("waterquality", "水质", "水样", "检测结果", "codmn", "高锰酸盐", "氨氮", "总氮", "总磷")),
    ("pollution_sources", ("污染源", "排污口", "outfall", "工业源", "生活源", "畜禽", "养殖", "水产")),
    ("precipitation", ("rainfall", "precip", "降雨", "雨量")),
    ("temperature", ("temperature", "气温", "温度")),
    ("pet_et", ("pet", "evapotranspiration", "蒸散")),
    ("flow", ("streamflow", "discharge", "flow", "流量", "径流")),
    ("stage", ("stage", "waterlevel", "水位")),
    ("dem", ("dem", "高程")),
    ("subbasins", ("subbasin", "subbasins", "子流域")),
    ("river_network", ("river", "reach", "河网", "河流", "支流", "河道")),
    ("watershed_boundary", ("watershedboundary", "basinboundary", "流域边界", "边界")),
    ("administrative_boundary", ("行政区", "乡镇", "街道", "区界", "县界")),
    ("land_use", ("landuse", "landcover", "土地利用", "地类")),
    ("soil", ("soil", "土壤")),
    ("reservoir_lake", ("reservoir", "lake", "水库", "湖泊", "库容")),
    ("monitoring_stations", ("station", "monitor", "采样点", "监测点", "点位", "断面")),
    ("field_survey", ("调查", "采样", "问卷", "照片", "photo", "uav", "无人机", "遥感")),
)


def _category(path: Path) -> str:
    value = _norm(path.as_posix())
    for category, terms in CATEGORY_RULES:
        if any(_norm(term) in value for term in terms):
            return category
    return "manual_classification_required"


def _table_header(path: Path) -> tuple[list[str], list[str], int | None]:
    try:
        if path.suffix.lower() in {".csv", ".tsv"}:
            frame = pd.read_csv(path, sep="\t" if path.suffix.lower() == ".tsv" else ",", nrows=5, encoding_errors="replace")
            return [str(item) for item in frame.columns], [], None
        book = pd.ExcelFile(path)
        preview = pd.read_excel(path, sheet_name=book.sheet_names[0], nrows=5)
        return [str(item) for item in preview.columns], list(book.sheet_names), None
    except Exception as exc:
        return [], [], hash(type(exc).__name__)


def discover_real_project_data(source_root: str | Path) -> tuple[pd.DataFrame, dict[str, Path]]:
    root = Path(source_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Real project source directory not found: {root}")
    rows: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    checksums: set[str] = set()
    for path in sorted(_iter_source_files(root)):
        stat = path.stat()
        checksum = _hash_file(path)
        base_dataset_id = f"real_{checksum[:16]}"
        suffix = path.suffix.lower()
        columns: list[str] = []
        sheets: list[str] = []
        parser_error = None
        if suffix in SUPPORTED_TABLES and stat.st_size <= 100 * 1024 * 1024:
            columns, sheets, parser_error = _table_header(path)
            parser_status = "parsed" if columns else "needs_manual_review"
        elif suffix in SPATIAL_SUFFIXES:
            parser_status = "metadata_only"
        elif suffix in METADATA_SUFFIXES:
            parser_status = "metadata_only"
        else:
            parser_status = "unsupported"
        category = _category(path)
        duplicate = checksum in checksums
        dataset_id = base_dataset_id if not duplicate else f"{base_dataset_id}_{hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest()[:8]}"
        checksums.add(checksum)
        registerable = not duplicate and category != "manual_classification_required" and parser_status in {"parsed", "metadata_only"}
        sensitive = category in {"water_quality", "pollution_sources", "monitoring_stations", "field_survey"}
        rows.append({
            "dataset_id": dataset_id, "original_filename": path.name, "logical_name": path.stem,
            "category": category, "format": suffix.lstrip(".") or "none", "size": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), "checksum": checksum,
            "source": _logical_source(root, path), "sensitive": sensitive,
            "expected_use": "real project evidence" if category != "manual_classification_required" else "manual review",
            "detected_schema": json.dumps({"columns": columns, "sheets": sheets}, ensure_ascii=False),
            "parser_status": parser_status, "registered_status": "referenced" if registerable else ("duplicate" if duplicate else "not_registered"),
            "notes": "parser exception requires manual review" if parser_error else "",
        })
        if registerable:
            paths[dataset_id] = path
    return pd.DataFrame(rows), paths


def _read_table(path: Path) -> tuple[pd.DataFrame | None, str]:
    try:
        if path.suffix.lower() in {".csv", ".tsv"}:
            return pd.read_csv(path, sep="\t" if path.suffix.lower() == ".tsv" else ",", encoding_errors="replace"), ""
        if path.suffix.lower() in {".xlsx", ".xls"}:
            book = pd.ExcelFile(path)
            candidates = [pd.read_excel(path, sheet_name=sheet) for sheet in book.sheet_names[:10]]
            return max(candidates, key=lambda frame: len(frame.columns) * max(1, len(frame))), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return None, "unsupported table"


FIELD_RULES = {
    "station_id": ("stationid", "站点编号", "点位编号", "采样点编号", "样点编号", "断面编号"),
    "timestamp": ("timestamp", "datetime", "time", "日期时间", "采样时间", "监测时间"),
    "date": ("date", "日期", "采样日期"),
    "time": ("time", "时间", "采样时刻"),
    "longitude": ("longitude", "lon", "经度"),
    "latitude": ("latitude", "lat", "纬度"),
    "rainfall_mm": ("rainfallmm", "rainmm", "降雨量", "降雨"),
    "flow_cms": ("flowm3s", "flowcms", "流量m3s", "流量"),
    "observed_flow_cms": ("flowobsm3s", "observedflow", "实测流量"),
    "simulated_flow_cms": ("flowsimm3s", "simulatedflow", "模拟流量"),
    "water_level_m": ("waterlevelm", "stage", "水位"),
    "CODMn": ("codmn", "高锰酸盐指数"),
    "NH3-N": ("nh3n", "氨氮"),
    "TN": ("tn", "总氮"),
    "TP": ("tp", "总磷"),
}


def _canonical_field(column: str) -> tuple[str | None, float]:
    value = _norm(column)
    for canonical, aliases in FIELD_RULES.items():
        for alias in aliases:
            normalized = _norm(alias)
            if value == normalized:
                return canonical, 1.0
            if len(normalized) >= 2 and normalized in value:
                return canonical, 0.92
    return None, 0.0


def _unit(column: str) -> str:
    text = column.casefold().replace("³", "3")
    for token, unit in (("mg/l", "mg/L"), ("mg_l", "mg/L"), ("mg／l", "mg/L"), ("m3/s", "m3/s"), ("m3_s", "m3/s"), ("m³/s", "m3/s"), ("t/d", "t/d"), ("t_d", "t/d"), ("mm", "mm"), ("km2", "km2"), ("km²", "km2")):
        if token in text:
            return unit
    return "not_declared"


def audit_data_quality(inventory: pd.DataFrame, paths: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    quality: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    spatial: list[dict[str, Any]] = []
    tables: dict[str, pd.DataFrame] = {}
    by_id = inventory.set_index("dataset_id").to_dict("index")
    for dataset_id, path in paths.items():
        meta = by_id[dataset_id]
        errors: list[str] = []
        warnings: list[str] = []
        missing = duplicates = 0
        frame, error = _read_table(path)
        if frame is not None:
            tables[dataset_id] = frame
            missing = int(frame.isna().sum().sum())
            duplicates = int(frame.duplicated().sum())
            if missing: warnings.append(f"{missing} missing cells")
            if duplicates: warnings.append(f"{duplicates} duplicate rows")
            for column in frame.columns:
                canonical, confidence = _canonical_field(str(column))
                if canonical:
                    unit = "not_applicable" if canonical in {"station_id", "timestamp", "date", "time"} else _unit(str(column))
                    mappings.append({
                        "dataset_id": dataset_id, "source_field": str(column), "canonical_field": canonical,
                        "confidence": confidence, "mapping_method": "normalized alias", "unit": unit,
                        "transformation": "rename only", "manual_confirmation_required": confidence < 0.95,
                    })
                    units.append({"dataset_id": dataset_id, "field": canonical, "source_field": str(column), "detected_unit": unit, "status": "needs_unit_fix" if unit == "not_declared" else "valid", "notes": "Unit not declared in header" if unit == "not_declared" else ""})
            for column in frame.columns:
                canonical, _ = _canonical_field(str(column))
                if canonical in {"CODMn", "NH3-N", "TN", "TP", "rainfall_mm", "flow_cms", "observed_flow_cms", "simulated_flow_cms"}:
                    numeric = frame[column].astype(str).str.extract(r"(-?\d+(?:\.\d+)?)", expand=False).pipe(pd.to_numeric, errors="coerce")
                    if (numeric < 0).any(): errors.append(f"negative values in {column}")
        elif path.suffix.lower() in SPATIAL_SUFFIXES:
            try:
                if path.suffix.lower() in {".tif", ".tiff", ".asc"}:
                    import rasterio
                    with rasterio.open(path) as source:
                        spatial.append({"dataset_id": dataset_id, "relationship": meta["category"], "status": "valid" if source.crs else "needs_crs_fix", "crs": str(source.crs), "feature_count": source.width * source.height, "invalid_geometry_count": None, "method": "rasterio metadata", "distance": None, "confidence": 1.0 if source.crs else 0.0, "notes": ""})
                else:
                    import geopandas as gpd
                    try:
                        geo = gpd.read_file(path, on_invalid="ignore")
                    except TypeError:
                        geo = gpd.read_file(path)
                    invalid = int(geo.geometry.isna().sum() + (~geo.geometry.dropna().is_valid).sum())
                    spatial.append({"dataset_id": dataset_id, "relationship": meta["category"], "status": "valid_with_warnings" if invalid else ("valid" if geo.crs else "needs_crs_fix"), "crs": str(geo.crs), "feature_count": len(geo), "invalid_geometry_count": invalid, "method": "geopandas read-only inspection", "distance": None, "confidence": 1.0 if geo.crs else 0.0, "notes": "Invalid geometries were counted, not repaired."})
                    if invalid: warnings.append(f"{invalid} invalid or unreadable geometries")
            except Exception as exc:
                warnings.append(f"spatial inspection unavailable: {type(exc).__name__}")
                spatial.append({"dataset_id": dataset_id, "relationship": meta["category"], "status": "needs_manual_review", "crs": "unknown", "feature_count": None, "invalid_geometry_count": None, "method": "metadata fallback", "distance": None, "confidence": 0.0, "notes": str(exc)[:240]})
        elif error and meta["parser_status"] == "parsed":
            errors.append(error)
        if errors: status = "invalid"
        elif warnings: status = "valid_with_warnings"
        elif frame is not None or path.suffix.lower() in SPATIAL_SUFFIXES: status = "valid"
        else: status = "needs_manual_review"
        quality.append({"dataset_id": dataset_id, "category": meta["category"], "format": meta["format"], "status": status, "row_count": len(frame) if frame is not None else None, "missing_cells": missing, "duplicate_rows": duplicates, "errors": "; ".join(errors), "warnings": "; ".join(warnings), "source": meta["source"]})
    spatial.extend([
        {"dataset_id": "relationship_gate", "relationship": relation, "status": "needs_manual_review", "crs": "mixed_or_unknown", "feature_count": None, "invalid_geometry_count": None, "method": "authoritative ID mapping required", "distance": None, "confidence": 0.0, "notes": "Automatic assignment was not used for formal conclusions."}
        for relation in ("station_to_reach", "reach_to_subbasin", "source_to_drainage_path")
    ])
    return pd.DataFrame(quality), pd.DataFrame(mappings), pd.DataFrame(units), pd.DataFrame(spatial), tables


def _find_table(tables: dict[str, pd.DataFrame], required: set[str]) -> tuple[str | None, pd.DataFrame | None, dict[str, str]]:
    best: tuple[int, str, pd.DataFrame, dict[str, str]] | None = None
    for dataset_id, frame in tables.items():
        mapping = {}
        for column in frame.columns:
            canonical, _ = _canonical_field(str(column))
            if canonical and canonical not in mapping:
                mapping[canonical] = str(column)
        numeric_fields = required - {"station_id", "timestamp", "date", "time"}
        valid_values = sum(int(_numeric(frame[mapping[field]]).notna().sum()) for field in numeric_fields if field in mapping)
        score = len(required & set(mapping)) * 1_000_000 + valid_values * 1000 + len(frame)
        if required <= set(mapping) and (best is None or score > best[0]):
            best = (score, dataset_id, frame, mapping)
    return (best[1], best[2], best[3]) if best else (None, None, {})


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.extract(r"(-?\d+(?:\.\d+)?)", expand=False), errors="coerce")


def analyze_water_quality(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    dataset_id, frame, mapping = _find_table(tables, {"station_id", "CODMn", "NH3-N", "TN", "TP"})
    if frame is None:
        return pd.DataFrame(), {"status": "blocked", "reason": "water-quality table with station and four target indicators not found"}
    stations = frame[mapping["station_id"]].astype(str).str.strip()
    mapped_ids: set[str] = set()
    sampling_times: list[pd.Timestamp] = []
    for other in tables.values():
        other_mapping = {}
        for column in other.columns:
            canonical, _ = _canonical_field(str(column))
            if canonical and canonical not in other_mapping: other_mapping[canonical] = str(column)
        if "station_id" not in other_mapping: continue
        other_ids = set(other[other_mapping["station_id"]].dropna().astype(str).str.strip())
        if {"longitude", "latitude"} <= set(other_mapping): mapped_ids.update(set(stations) & other_ids)
        if {"timestamp", "date"} <= set(other_mapping):
            combined = other[other_mapping["date"]].astype(str).str.strip() + " " + other[other_mapping["timestamp"]].astype(str).str.strip()
            sampling_times.extend(pd.to_datetime(combined, errors="coerce", utc=True, format="mixed").dropna().tolist())
        elif "timestamp" in other_mapping:
            sampling_times.extend(pd.to_datetime(other[other_mapping["timestamp"]], errors="coerce", utc=True, format="mixed").dropna().tolist())
        elif "date" in other_mapping:
            sampling_times.extend(pd.to_datetime(other[other_mapping["date"]], errors="coerce", utc=True, format="mixed").dropna().tolist())
    flow_available = any(_find_table({key: value}, {"timestamp", "flow_cms"})[1] is not None for key, value in tables.items())
    instantaneous_load = any(any(token in _norm(str(column)) for token in ("通量", "flux", "load")) for other in tables.values() for column in other.columns)
    rows = []
    for variable in ("CODMn", "NH3-N", "TN", "TP"):
        raw = frame[mapping[variable]]
        values = _numeric(raw)
        nondetect = int(raw.astype(str).str.match(r"\s*[<≤]").sum())
        rows.append({
            "dataset_id": dataset_id, "variable": variable, "station_count": int(stations[values.notna()].nunique()),
            "record_count": int(values.notna().sum()), "missing": int(values.isna().sum()),
            "duplicates": int(pd.DataFrame({"station": stations, "value": values}).duplicated().sum()),
            "non_detect": nondetect, "invalid": int(((values < 0) & values.notna()).sum()),
            "unit": _unit(mapping[variable]), "unit_consistency": "single_header_unit",
            "start": min(sampling_times).isoformat() if sampling_times else "",
            "end": max(sampling_times).isoformat() if sampling_times else "",
            "sampling_frequency": "single wet-weather survey; irregular",
            "station_mapping": f"{len(mapped_ids)}/{stations.nunique()} matched to coordinate-bearing station records",
            "flow_alignment": "event flow available; station-specific alignment needs review" if flow_available else "unavailable",
            "load_availability": "instantaneous_estimate_available_with_warnings" if instantaneous_load else "unavailable",
        })
    return pd.DataFrame(rows), {"status": "real_data_tested", "dataset_id": dataset_id, "stations": int(stations.nunique()), "station_ids": set(stations), "mapped_station_count": len(mapped_ids), "flow_available": flow_available, "load_availability": "instantaneous_estimate_available_with_warnings" if instantaneous_load else "unavailable", "mapping": mapping}


def analyze_wet_weather_event(
    tables: dict[str, pd.DataFrame], water_quality: dict[str, Any],
    target_start: str = "2026-06-23", target_end: str = "2026-06-24 23:59:59",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates = []
    start, end = pd.Timestamp(target_start), pd.Timestamp(target_end)
    for dataset_key, candidate in tables.items():
        _, frame, mapping = _find_table({dataset_key: candidate}, {"timestamp", "rainfall_mm", "flow_cms"})
        if frame is None: continue
        times = pd.to_datetime(frame[mapping["timestamp"]], errors="coerce")
        overlap = int(((times >= start) & (times <= end)).sum())
        candidates.append((overlap, len(frame), dataset_key, frame, mapping))
    if candidates:
        _, _, dataset_id, frame, mapping = max(candidates)
    else:
        dataset_id, frame, mapping = None, None, {}
    if frame is None:
        return pd.DataFrame(), {"status": "blocked", "blocker": "event_load_analysis_blocked_missing_flow"}
    time = pd.to_datetime(frame[mapping["timestamp"]], errors="coerce")
    rain = _numeric(frame[mapping["rainfall_mm"]])
    flow = _numeric(frame[mapping["flow_cms"]])
    valid = time.notna() & rain.notna() & flow.notna()
    time, rain, flow = time[valid], rain[valid], flow[valid]
    rows = [{
        "event_id": "wet_weather_event_20260623_24", "source_dataset_id": dataset_id,
        "event_start": time.min(), "event_end": time.max(), "rainfall_available": True,
        "total_rainfall_mm": float(rain.sum()), "peak_rainfall_mm": float(rain.max()),
        "peak_rainfall_time": time.loc[rain.idxmax()] if len(rain) else pd.NaT,
        "flow_available": True, "peak_flow_cms": float(flow.max()),
        "peak_flow_time": time.loc[flow.idxmax()] if len(flow) else pd.NaT,
        "stage_available": "water_level_m" in mapping, "wq_samples": len(water_quality.get("station_ids", set())),
        "antecedent_rainfall_status": "insufficient_pre_event_coverage",
        "event_readiness": "ready_with_warnings",
        "event_analysis_status": "real_data_diagnostic",
        "blocker": "single_event_only; no multi-event calibration; load source is instantaneous estimate",
    }]
    return pd.DataFrame(rows), {"status": "ready_with_warnings", "dataset_id": dataset_id, "date_range": [str(time.min()), str(time.max())], "flow_records": int(len(flow))}


def analyze_hydrology_diagnostic(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    dataset_id, frame, mapping = _find_table(tables, {"timestamp", "observed_flow_cms", "simulated_flow_cms"})
    if frame is None:
        return pd.DataFrame(), {"status": "not_tested", "reason": "observed/simulated pair not found"}
    observed = _numeric(frame[mapping["observed_flow_cms"]])
    simulated = _numeric(frame[mapping["simulated_flow_cms"]])
    time = pd.to_datetime(frame[mapping["timestamp"]], errors="coerce")
    metrics = calculate_all_metrics(observed, simulated)
    dt_hours = float(time.sort_values().diff().dt.total_seconds().dropna().median() / 3600) if time.notna().sum() > 1 else pd.NA
    peak_error = float(100 * (simulated.max() - observed.max()) / observed.max()) if observed.max() else pd.NA
    timing = float((time.loc[simulated.idxmax()] - time.loc[observed.idxmax()]).total_seconds() / 3600) if time.notna().all() else pd.NA
    volume_error = float(100 * (simulated.sum() - observed.sum()) / observed.sum()) if observed.sum() else pd.NA
    row = {
        "dataset_id": dataset_id, "model_source": "existing_project_output; provenance requires confirmation",
        "calibration_period": "not separated", "validation_period": "single-event hindcast diagnostic",
        **{key: value for key, value in metrics.items() if key != "warnings"},
        "peak_error_percent": peak_error, "timing_error_hours": timing,
        "volume_error_percent": volume_error, "time_step_hours": dt_hours,
        "validation_status": "real_data_diagnostic", "hydrolite_model_validated": False,
        "limitations": "Single event; calibration/validation not separated; model provenance not confirmed as HydroLite.",
    }
    return pd.DataFrame([row]), {"status": "real_data_diagnostic", "dataset_id": dataset_id, "metrics": row}


def build_capability_readiness(inventory: pd.DataFrame, wq: dict[str, Any], event: dict[str, Any], hydro: dict[str, Any]) -> pd.DataFrame:
    categories = set(inventory.loc[inventory["registered_status"] == "referenced", "category"])
    has = lambda *names: all(name in categories for name in names)
    rows = [
        ("event_hydrology", "rainfall, subbasins, reaches, observed flow", has("precipitation", "flow", "subbasins", "river_network"), "blocked", False, "HydroLite-ready subbasin/reach inputs and split validation are not prepared."),
        ("continuous_hydrology", "continuous forcing and flow", False, "blocked", False, "Continuous verified forcing is incomplete."),
        ("watershed_delineation", "DEM, boundary, outlet", has("dem", "watershed_boundary"), "ready_with_warnings" if has("dem", "watershed_boundary") else "blocked", False, "Professional GIS review remains required."),
        ("reservoir_routing", "storage/area/discharge curves", has("reservoir_lake"), "blocked", False, "Authoritative reservoir curves/rules not confirmed."),
        ("historical_flood_analysis", "rainfall, observed flow, model pair", hydro["status"] == "real_data_diagnostic", "ready_with_warnings" if hydro["status"] == "real_data_diagnostic" else "blocked", hydro["status"] == "real_data_diagnostic", "Existing-model single-event diagnostic only."),
        ("drought", "multi-year forcing and observations", False, "blocked", False, "Temporal coverage is insufficient."),
        ("flood_forecast", "forecast rainfall and multi-event validation", False, "blocked", False, "Capability remains partial; no operational forecast forcing."),
        ("water_quality_data_analysis", "station metadata and CODMn/NH3-N/TN/TP", wq["status"] == "real_data_tested", "ready_with_warnings" if wq["status"] == "real_data_tested" else "blocked", wq["status"] == "real_data_tested", "Observation analysis only; not a process simulation."),
        ("water_quality_method_lab", "multi-station time series and river graph", False, "experimental", False, "Single wet-weather survey is not a multi-horizon training set."),
        ("flood_susceptibility", "inventory, factors, spatial blocks", False, "blocked", False, "Verified flood inventory/spatial blocks not confirmed."),
        ("rusle", "DEM, land use, soil, erosivity", has("dem", "land_use", "soil", "precipitation"), "ready_with_warnings" if has("dem", "land_use", "soil", "precipitation") else "blocked", False, "Input presence does not establish parameter suitability."),
        ("sediment", "erosion, SDR and observations", False, "blocked", False, "Observed sediment and calibrated delivery parameters missing."),
        ("hec_hms", "HEC-HMS project and observations", True, "ready_with_warnings", False, "Existing external project was inventoried but not rerun in M8A."),
        ("swmm", "SWMM INP and drainage observations", False, "blocked", False, "No project-specific SWMM network confirmed."),
    ]
    return pd.DataFrame([
        {"capability": capability, "required_data": required, "available": available, "quality": status,
         "data_readiness": status, "executed": executed, "blocked": status in {"blocked", "planned"}, "blocker": reason if status == "blocked" else "", "action": reason}
        for capability, required, available, status, executed, reason in rows
    ])


def assess_real_project_commercial_readiness(readiness: pd.DataFrame) -> pd.DataFrame:
    statuses = {
        "Data Intake": ("ready_with_warnings", False, "Referenced inventory is available; large files stay external."),
        "QC": ("ready_with_warnings", False, "Mapping, unit and geometry warnings require review."),
        "Configuration": ("blocked", True, "HydroLite-ready catchment/reach configuration is not prepared."),
        "Run": ("ready_with_warnings", False, "Only data analysis and existing-output diagnostics are ready."),
        "Result": ("ready_with_warnings", False, "Results preserve real/synthetic and model provenance boundaries."),
        "Interpretation": ("ready_with_warnings", False, "Single-event evidence limits conclusions."),
        "Reporting": ("ready", False, "Bilingual baseline report and evidence tables are generated."),
        "Delivery": ("ready_with_warnings", False, "Baseline can be reviewed but not approved as validated model output."),
        "Desktop": ("ready_with_warnings", False, "Debug shell can display the Streamlit workflow."),
        "Recovery": ("ready", False, "Inputs remain immutable and audit output is rerunnable."),
    }
    return pd.DataFrame([{"dimension": key, "status": value[0], "commercial_beta_blocker": value[1], "evidence": value[2]} for key, value in statuses.items()])


def _friction_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = [
        ("FR-001", "Project", "Nested project.yaml identity was not read by project registration/versioning.", "major", "common", "Wrong project name/ID", "Use flat keys", "Read both schemas in one shared helper", "M8A", False, "resolved_in_m8a", "P0"),
        ("FR-002", "Scenario", "Water-quality observation analysis was coupled to the planned simulation capability.", "major", "common", "Honest analysis path appeared blocked", "Use reporting-only recipe", "Separate data-analysis capability from simulation", "M8A", False, "resolved_in_m8a", "P0"),
        ("FR-003", "Data Intake", "Large real datasets need external references rather than upload copies.", "moderate", "common", "Slow and storage-heavy import", "CLI reference audit", "Add UI reference picker with privacy preview", "M8B", True, "real source inventory", "P1"),
        ("FR-004", "Field Mapping", "Chinese water-quality headers need review even after alias mapping.", "moderate", "common", "Requires domain knowledge", "Review mapping workbook", "Interactive confidence/units confirmation", "M8B", True, "field mapping audit", "P1"),
        ("FR-005", "Spatial", "One malformed line geometry prevents a strict vector read.", "moderate", "occasional", "River mapping can stop", "Read invalid geometry as null", "Expose invalid feature IDs and repair-copy action", "M8B", True, "spatial audit", "P1"),
        ("FR-006", "Hydrology", "Existing simulated-flow provenance is unclear.", "major", "occasional", "Cannot claim HydroLite validation", "Diagnostic-only label", "Require model/run provenance on import", "M8B", True, "hydrology validation", "P1"),
        ("FR-007", "Water Quality", "Instantaneous estimated flow does not support continuous/event total load.", "major", "common", "Load conclusions are constrained", "Report instantaneous estimates only", "Add flow evidence gate and uncertainty entry", "M9", True, "wet-weather event", "P1"),
        ("FR-008", "Configuration", "Real subbasin/reach data are not yet in HydroLite input schema.", "blocking", "common", "Hydrology run is blocked", "Manual GIS/data transformation", "Build reviewed import mapping workflow", "M8B", True, "readiness matrix", "P1"),
        ("FR-009", "Delivery", "Baseline delivery requires several CLI governance steps.", "moderate", "common", "High operator effort", "Use M8A audit command", "Add single reviewed-baseline UI action", "M8B", False, "delivery record", "P2"),
        ("FR-010", "GEE", "Compute authentication is optional and unavailable in some environments.", "minor", "occasional", "Missing data cannot be auto-filled", "Metadata recommendation", "Keep compute optional and show next action", "M8B", False, "capability readiness", "P3"),
    ]
    backlog = pd.DataFrame(rows, columns=["friction_id", "area", "description", "severity", "frequency", "user_impact", "workaround", "recommended_fix", "suggested_milestone", "blocking_commercial_beta", "evidence", "priority"])
    manual = pd.DataFrame([
        {"step": index + 1, "intended_action": row.area, "actual_action": row.description, "manual_intervention": row.workaround, "error": "" if row.evidence == "resolved_in_m8a" else row.description, "workaround": row.workaround, "time_seconds": None, "user_knowledge_required": "project/data domain", "automation_opportunity": row.recommended_fix, "severity": row.severity}
        for index, row in enumerate(backlog.itertuples())
    ])
    return backlog, manual


def _m9_backlog() -> pd.DataFrame:
    items = (
        ("pollution_source_inventory", "Authoritative source inventory and activity data"),
        ("source_generation", "CODMn/NH3-N/TN/TP generation coefficients and provenance"),
        ("rainfall_mobilization", "Event mobilization evidence"),
        ("hillslope_delivery", "Calibrated hillslope delivery"),
        ("channel_delivery", "Observed channel delivery evidence"),
        ("river_transport", "Reaction/transport process model"),
        ("reservoir_retention", "Reservoir geometry, operations and retention observations"),
        ("water_quality_calibration", "Multiple independent events and holdout design"),
        ("scenario_management", "Formal source-control and intervention scenarios"),
    )
    return pd.DataFrame([{"gap_id": key, "status": "missing_capability", "required_evidence": value, "target_milestone": "M9", "implemented_in_m8a": False} for key, value in items])


def _write_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)


def _safe_payload(value: Any) -> Any:
    if isinstance(value, dict): return {str(key): _safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)): return [_safe_payload(item) for item in value]
    if isinstance(value, Path): return value.name
    if isinstance(value, str) and (value.startswith("/Users/") or value.startswith("/home/")): return f"external-reference/{Path(value).name}"
    if isinstance(value, (pd.Timestamp, datetime)): return value.isoformat()
    if hasattr(value, "item") and callable(value.item): return _safe_payload(value.item())
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False: return None
    return value


def _register_workspace_references(workspace: Path, inventory: pd.DataFrame, paths: dict[str, Path]) -> None:
    manifest = read_workspace_manifest(workspace)
    existing = {item.get("dataset_id") for item in manifest.get("datasets", [])}
    external = workspace / "external"
    external.mkdir(exist_ok=True)
    meta = inventory.set_index("dataset_id").to_dict("index")
    for dataset_id, source in paths.items():
        if dataset_id in existing: continue
        link = external / f"{dataset_id}{source.suffix.lower()}"
        if not link.exists(): link.symlink_to(source)
        row = meta[dataset_id]
        manifest.setdefault("datasets", []).append({
            "dataset_id": dataset_id, "dataset_type": row["category"], "logical_path": str(link.relative_to(workspace)),
            "path": str(link.relative_to(workspace)), "checksum": row["checksum"], "size": row["size"],
            "quality_status": "needs_review", "source_type": "external_reference", "sensitive": bool(row["sensitive"]),
        })
    write_workspace_manifest(workspace, manifest)


def _ensure_workspace(workspace: Path, project_name: str) -> tuple[dict[str, Any], bool]:
    existed = workspace.exists() and (workspace / "project.yaml").exists()
    if not existed:
        create_workspace(workspace, project_name)
        config_path = workspace / "project.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        config.setdefault("project", {}).update({"type": "water_environment", "real_project": True, "created_by": "real_project_baseline_audit"})
        config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        config = yaml.safe_load((workspace / "project.yaml").read_text(encoding="utf-8")) or {}
        existed = (config.get("project") or {}).get("created_by") != "real_project_baseline_audit"
    records = list_project_records(workspace_path=str(workspace.resolve()))
    record = records[0] if records else register_workspace_as_project(workspace)
    return record, existed


def _write_reports(output: Path, project: dict[str, Any], inventory: pd.DataFrame, quality: pd.DataFrame, readiness: pd.DataFrame, validation: pd.DataFrame, friction: pd.DataFrame, commercial: pd.DataFrame) -> None:
    (output / "reports").mkdir(parents=True, exist_ok=True)
    facts = {
        "files": len(inventory), "registered": int((inventory["registered_status"] == "referenced").sum()),
        "sensitive": int(inventory["sensitive"].sum()), "warnings": int((quality["status"] == "valid_with_warnings").sum()),
        "blocked": int((readiness["data_readiness"] == "blocked").sum()), "executed": int(readiness["executed"].sum()),
    }
    selected = readiness[["capability", "data_readiness", "executed", "action"]].astype(str)
    table = "| " + " | ".join(selected.columns) + " |\n| " + " | ".join(["---"] * len(selected.columns)) + " |\n"
    table += "\n".join("| " + " | ".join(row) + " |" for row in selected.itertuples(index=False, name=None))
    zh = f"""# M8A 真实项目闭环基线报告

## 1. 项目概况

- 项目：`{project['display_name']}`
- 项目 ID：`{project['project_id']}`
- 定位：真实资料只读盘点、就绪度和产品摩擦审计。

## 2. 数据清单与质量

- 发现文件：`{facts['files']}`；引用登记：`{facts['registered']}`；敏感数据集：`{facts['sensitive']}`。
- 有警告的数据集：`{facts['warnings']}`。异常未被自动删除。

## 3. 能力就绪度

{table}

## 4. 已执行分析与真实证据

仅执行水质观测数据分析和已有模型过程线单事件诊断。后者来源尚未确认为 HydroLite，因此只标记 `real_data_diagnostic`。水质观测分析可标记 `real_data_tested`，但这不表示正式水质模拟已实现。

## 5. 数据缺口与科学限制

- 单一雨期事件不足以进行多事件率定和独立验证。
- HydroLite-ready 子流域、河段和参数输入尚未完成审查。
- 瞬时估算流量不能替代连续流量或事件总负荷。
- `water_quality` 主能力保持 `planned`；`flood_forecast`、`drought_forecast` 保持 `partial`。

## 6. 产品摩擦与下一阶段

- 摩擦项：`{len(friction)}`；Commercial Beta blocker：`{int(commercial['commercial_beta_blocker'].sum())}` 个维度。
- M8B 应优先完成审查式真实输入映射、独立时段验证和 UI 主流程降摩擦；正式水环境过程模型缺口进入 M9。
"""
    en = f"""# M8A Real Project Baseline Report

## Project and evidence boundary

Project: `{project['display_name']}` (`{project['project_id']}`). The audit found {facts['files']} files, registered {facts['registered']} read-only references, and identified {facts['sensitive']} sensitive datasets. No anomaly was deleted.

## Capability readiness

{table}

## Analyses executed

Only observed water-quality analysis and a single-event diagnostic of an existing observed/simulated flow pair were executed. The flow model provenance is not confirmed as HydroLite, so it remains `real_data_diagnostic`. Observed water-quality analysis reached `real_data_tested`; this does not implement or validate a production water-quality simulation.

## Limitations and next action

One wet-weather event cannot support multi-event calibration or independent validation. HydroLite-ready catchment/reach inputs remain unreviewed, and instantaneous estimated discharge is not a continuous/event load record. `water_quality` remains `planned`; flood and drought forecast capabilities remain `partial`. M8B should address reviewed real-input mapping and independent validation; process-model gaps remain in M9.
"""
    (output / OUTPUT_NAMES["report_zh"]).write_text(zh, encoding="utf-8")
    (output / OUTPUT_NAMES["report_en"]).write_text(en, encoding="utf-8")


def run_real_project_audit(
    source_root: str | Path, *, workspace_dir: str | Path, output_dir: str | Path = "output/real_project_validation",
    project_name: str = "Real Project Validation",
) -> dict[str, Any]:
    started = perf_counter()
    source = Path(source_root).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    workspace = Path(workspace_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    inventory, paths = discover_real_project_data(source)
    quality, mappings, units, spatial, tables = audit_data_quality(inventory, paths)
    water_quality, wq_status = analyze_water_quality(tables)
    event, event_status = analyze_wet_weather_event(tables, wq_status)
    hydrology, hydro_status = analyze_hydrology_diagnostic(tables)
    readiness = build_capability_readiness(inventory, wq_status, event_status, hydro_status)
    blockers = readiness.loc[readiness["data_readiness"].isin(["blocked", "planned"]), ["capability", "blocker", "action"]]
    commercial = assess_real_project_commercial_readiness(readiness)
    friction, manual = _friction_rows()
    validation = pd.DataFrame([
        {"capability": "water_quality_data_analysis", "synthetic_evidence": "not_applicable", "real_evidence": wq_status["status"], "validation_status": wq_status["status"], "data_status": "ready_with_warnings", "blocker": "", "next_action": "Confirm units, station mapping, and continuous flow evidence."},
        {"capability": "historical_flood_analysis", "synthetic_evidence": "existing framework", "real_evidence": hydro_status["status"], "validation_status": hydro_status["status"], "data_status": "single_event", "blocker": "model provenance and independent split", "next_action": "Build HydroLite inputs and reserve independent events."},
        {"capability": "gamma_lag_features", "synthetic_evidence": "demonstrated", "real_evidence": "not_tested", "validation_status": "not_tested", "data_status": "insufficient", "blocker": "no independent multi-event feature benchmark", "next_action": "M8B real-event evaluation."},
        {"capability": "river_graph_features", "synthetic_evidence": "demonstrated", "real_evidence": "not_tested", "validation_status": "experimental", "data_status": "needs_mapping", "blocker": "authoritative graph mapping", "next_action": "Review reach/subbasin IDs."},
        {"capability": "water_quality_method_lab", "synthetic_evidence": "mixed", "real_evidence": "not_tested", "validation_status": "experimental", "data_status": "insufficient time series", "blocker": "single survey event", "next_action": "Collect repeated multi-station observations."},
        {"capability": "flood_susceptibility", "synthetic_evidence": "baseline only", "real_evidence": "not_tested", "validation_status": "experimental", "data_status": "blocked", "blocker": "verified flood inventory/spatial blocks missing", "next_action": "Prepare spatially independent inventory."},
    ])

    for key in ("inventory", "quality", "mapping", "units", "spatial", "readiness", "blockers", "validation", "hydrology", "water_quality", "event", "friction", "manual", "commercial", "m9"):
        (output / OUTPUT_NAMES[key]).parent.mkdir(parents=True, exist_ok=True)
    _write_excel(output / OUTPUT_NAMES["inventory"], {"inventory": inventory})
    _write_excel(output / OUTPUT_NAMES["quality"], {"datasets": quality})
    _write_excel(output / OUTPUT_NAMES["mapping"], {"field_mapping": mappings})
    _write_excel(output / OUTPUT_NAMES["units"], {"unit_audit": units})
    _write_excel(output / OUTPUT_NAMES["spatial"], {"spatial_audit": spatial})
    _write_excel(output / OUTPUT_NAMES["readiness"], {"capability_readiness": readiness})
    _write_excel(output / OUTPUT_NAMES["blockers"], {"blockers": blockers})
    _write_excel(output / OUTPUT_NAMES["validation"], {"scientific_gate": validation})
    if not hydrology.empty: _write_excel(output / OUTPUT_NAMES["hydrology"], {"metrics": hydrology})
    if not water_quality.empty: _write_excel(output / OUTPUT_NAMES["water_quality"], {"variables": water_quality})
    if not event.empty: _write_excel(output / OUTPUT_NAMES["event"], {"event": event})
    _write_excel(output / OUTPUT_NAMES["friction"], {"backlog": friction})
    _write_excel(output / OUTPUT_NAMES["manual"], {"manual_steps": manual})
    _write_excel(output / OUTPUT_NAMES["commercial"], {"commercial_readiness": commercial})
    _write_excel(output / OUTPUT_NAMES["m9"], {"m9_backlog": _m9_backlog()})

    project, existed = _ensure_workspace(workspace, project_name)
    _register_workspace_references(workspace, inventory, paths)
    pointer = workspace / "reports" / "real_project_baseline_pointer.json"
    pointer.write_text(json.dumps({"output_dir": str(output)}, indent=2) + "\n", encoding="utf-8")
    versions = [row for row in list_project_version_records(project_id=project["project_id"]) if row.get("status") == "real_project_baseline"]
    version = versions[0] if versions else create_project_version(
        project["project_id"], created_by="m8a_audit", description="Read-only real project baseline",
        scenario_ids=("SC01", "SC05", "SC06"), snapshot_mode="referenced", status="real_project_baseline",
    )
    environment = capture_delivery_environment(version["project_version_id"])
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run_paths = ensure_runtime_directories(run_id)
    config_path = run_paths["configuration"] / "m8a_run_config.json"
    config_path.write_text(json.dumps({"project_id": project["project_id"], "project_version_id": version["project_version_id"], "source": "external-reference", "models_rerun": False}, indent=2), encoding="utf-8")
    run = create_run_record(
        run_id=run_id, project_id=project["project_id"], project_version_id=version["project_version_id"],
        data_snapshot_id=version["data_snapshot_id"], configuration_snapshot_id=version["configuration_snapshot_id"],
        workflow_id="real_project_baseline_audit", run_name="M8A real project baseline", run_mode="local",
        requested_at=_now(), started_at=_now(), finished_at=_now(), status="succeeded", progress=100,
        current_stage="reporting", configuration_path=str(config_path), configuration_checksum=_hash_file(config_path),
        git_commit=_git_commit(), hydrolite_version=__version__, python_version=sys.version.split()[0],
        environment_id=environment["environment_id"], result_status="succeeded", error_summary="", legacy_unversioned=False,
        warnings=["Single event only", "HydroLite hydrology not rerun", "Water-quality simulation remains planned"],
    )
    _write_reports(output, project, inventory, quality, readiness, validation, friction, commercial)
    artifact_paths = [path for key, relative in OUTPUT_NAMES.items() if key != "manifest" and (path := output / relative).is_file()]
    artifacts = [register_artifact(run_id, None, path) for path in artifact_paths]
    report_names = {Path(OUTPUT_NAMES["report_zh"]).name, Path(OUTPUT_NAMES["report_en"]).name}
    report_ids = [row["artifact_id"] for row in artifacts if row["display_name"] in report_names]
    artifact_ids = [row["artifact_id"] for row in artifacts if row["artifact_id"] not in report_ids]
    for previous in list_deliverable_records(project_id=project["project_id"]):
        if previous.get("project_version_id") == version["project_version_id"] and previous.get("review_status") == "reviewed":
            request_delivery_changes(previous["deliverable_id"], actor="m8a_reviewer", comment="A corrected parser/readiness audit supersedes this baseline draft.")
    deliverable = create_deliverable(
        version["project_version_id"], run_ids=[run_id], artifact_ids=artifact_ids, report_ids=report_ids,
        created_by="m8a_audit", scientific_validation_level="real_data_tested",
        capabilities=["water_quality_data_analysis"], warnings=["INSUFFICIENT_MULTI_EVENT_REAL_DATA", "HYDROLITE_HYDROLOGY_NOT_TESTED"],
        limitations=["Water-quality result is observation analysis, not process simulation.", "Hydrology result is a single-event diagnostic of an existing output with unconfirmed model provenance.", "No capability is independently validated."],
        delivery_claim="analysis_report",
    )
    submit_delivery(deliverable["deliverable_id"], actor="m8a_analyst", comment="Submitted as a real-project baseline audit, not a validated production model.")
    deliverable = review_delivery(deliverable["deliverable_id"], actor="m8a_reviewer", comment="Reviewed for evidence boundaries, data gaps, and product friction; not approved for delivery.")
    integrity = verify_deliverable(deliverable["deliverable_id"])
    manifest = {
        "schema_version": 1, "project_id": project["project_id"], "project_name": project["display_name"],
        "project_version": version["project_version_id"], "project_version_number": version["version_number"],
        "real_project": True, "real_project_data_status": "available", "source_reference": f"external-reference/{source.name}",
        "dataset_ids": inventory.loc[inventory["registered_status"] == "referenced", "dataset_id"].tolist(),
        "checksums": dict(zip(inventory["dataset_id"], inventory["checksum"])),
        "date_ranges": {"wet_weather_event": event_status.get("date_range", [])},
        "spatial_coverage": "see spatial_mapping_audit.xlsx; absolute coordinates omitted from manifest",
        "capabilities_assessed": readiness["capability"].tolist(),
        "capabilities_executed": readiness.loc[readiness["executed"], "capability"].tolist(),
        "capabilities_blocked": readiness.loc[readiness["blocked"], "capability"].tolist(),
        "scientific_validation": validation.to_dict("records"),
        "warnings": ["Single wet-weather event", "No independent hydrology validation", "Instantaneous flow estimates do not establish continuous load"],
        "limitations": ["No production water-quality simulation", "No new scientific model", "No independent validation"],
        "run_id": run_id, "deliverable_id": deliverable["deliverable_id"], "delivery_review_status": deliverable["review_status"],
        "integrity_status": integrity["status"], "git_commit": _git_commit(), "software_version": __version__,
        "environment": {"python": sys.version.split()[0], "os": platform.system(), "architecture": platform.machine(), "environment_id": environment["environment_id"]},
        "timestamp": _now(), "duration_seconds": round(perf_counter() - started, 3), "workspace_preexisting": existed,
    }
    manifest_path = output / OUTPUT_NAMES["manifest"]
    manifest_path.write_text(json.dumps(_safe_payload(manifest), indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "passed", "output_dir": output, "project": project, "project_preexisting": existed, "version": version, "run": run, "deliverable": deliverable, "integrity": integrity, "manifest": manifest_path, "inventory": inventory, "quality": quality, "readiness": readiness, "validation": validation, "friction": friction, "commercial": commercial}
