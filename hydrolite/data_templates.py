from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
from typing import Any, Callable

import pandas as pd


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "data"


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    path: Path
    description: str
    required_fields: list[str]
    numeric_fields: list[str]
    time_fields: list[str]
    example_path: Path | None = None


def _specs() -> dict[str, TemplateSpec]:
    examples = TEMPLATE_ROOT / "examples"
    return {
        "rainfall": TemplateSpec(
            "rainfall",
            TEMPLATE_ROOT / "rainfall_template.csv",
            "Rainfall time series for one basin or a prepared project forcing table.",
            ["time", "rainfall_mm"],
            ["rainfall_mm"],
            ["time"],
            examples / "rainfall_example.csv",
        ),
        "subbasins": TemplateSpec(
            "subbasins",
            TEMPLATE_ROOT / "subbasins_template.csv",
            "Subbasin attributes for SCS-CN runoff and unit hydrograph routing.",
            ["subbasin_id", "area_km2", "cn", "initial_abstraction_ratio", "lag_time_hr", "outlet_reach_id"],
            ["area_km2", "cn", "initial_abstraction_ratio", "lag_time_hr"],
            [],
            examples / "subbasins_example.csv",
        ),
        "reaches": TemplateSpec(
            "reaches",
            TEMPLATE_ROOT / "reaches_template.csv",
            "River reach attributes for simplified Muskingum routing.",
            ["reach_id", "upstream_reach_id", "downstream_reach_id", "length_km", "slope", "muskingum_k_hr", "muskingum_x"],
            ["length_km", "slope", "muskingum_k_hr", "muskingum_x"],
            [],
            examples / "reaches_example.csv",
        ),
        "observed_streamflow": TemplateSpec(
            "observed_streamflow",
            TEMPLATE_ROOT / "observed_streamflow_template.csv",
            "Observed streamflow table for model evaluation.",
            ["time", "flow_cms", "station_id"],
            ["flow_cms"],
            ["time"],
            examples / "observed_streamflow_example.csv",
        ),
        "swmm_inflow_mapping": TemplateSpec(
            "swmm_inflow_mapping",
            TEMPLATE_ROOT / "swmm_inflow_mapping_template.csv",
            "Mapping from HydroLite outputs to SWMM node inflows.",
            ["hydrolite_output_id", "swmm_node_id", "scale_factor"],
            ["scale_factor"],
            [],
            examples / "swmm_inflow_mapping_example.csv",
        ),
        "gee_basin_boundary": TemplateSpec(
            "gee_basin_boundary",
            TEMPLATE_ROOT / "gee_basin_boundary_template.geojson",
            "GeoJSON Polygon or MultiPolygon basin boundary for GEE summaries.",
            [],
            [],
            [],
            examples / "gee_basin_boundary_example.geojson",
        ),
    }


def _result(name: str, path: str | Path) -> dict[str, Any]:
    return {
        "template_name": name,
        "path": str(Path(path)),
        "status": "passed",
        "errors": [],
        "warnings": [],
        "fields": [],
        "rows": 0,
    }


def _fail(result: dict[str, Any], message: str) -> dict[str, Any]:
    result["status"] = "failed"
    result["errors"].append(message)
    return result


def _warn(result: dict[str, Any], message: str) -> None:
    if result["status"] == "passed":
        result["status"] = "warning"
    result["warnings"].append(message)


def list_data_templates() -> list[dict[str, Any]]:
    rows = []
    for spec in _specs().values():
        rows.append(
            {
                "template_name": spec.name,
                "template_path": str(spec.path),
                "example_path": str(spec.example_path) if spec.example_path else "",
                "description": spec.description,
                "required_fields": spec.required_fields,
                "numeric_fields": spec.numeric_fields,
                "time_fields": spec.time_fields,
            }
        )
    return rows


def get_data_template(template_name: str) -> TemplateSpec:
    specs = _specs()
    if template_name not in specs:
        raise KeyError(f"Unknown data template: {template_name}. Available: {', '.join(specs)}")
    return specs[template_name]


def export_data_template(template_name: str, output_dir: str | Path) -> Path:
    spec = get_data_template(template_name)
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / spec.path.name
    shutil.copy2(spec.path, target)
    return target


def export_all_data_templates(output_dir: str | Path) -> list[Path]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    examples_dir = output / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    for spec in _specs().values():
        written.append(export_data_template(spec.name, output))
        if spec.example_path and spec.example_path.exists():
            target = examples_dir / spec.example_path.name
            shutil.copy2(spec.example_path, target)
            written.append(target)
    return written


def _read_csv_for_validation(path: str | Path, spec: TemplateSpec) -> tuple[dict[str, Any], pd.DataFrame | None]:
    csv_path = Path(path)
    result = _result(spec.name, csv_path)
    if not csv_path.exists():
        return _fail(result, f"File not found: {csv_path}"), None
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return _fail(result, f"CSV could not be read: {exc}"), None
    result["fields"] = list(df.columns)
    result["rows"] = int(len(df))
    missing = [field for field in spec.required_fields if field not in df.columns]
    if missing:
        _fail(result, f"Missing required fields: {', '.join(missing)}")
    return result, df


def _validate_csv(path: str | Path, spec: TemplateSpec, extra_checks: Callable[[dict[str, Any], pd.DataFrame], None] | None = None) -> dict[str, Any]:
    result, df = _read_csv_for_validation(path, spec)
    if df is None:
        return result
    if df.empty:
        _warn(result, "CSV has no data rows. This is acceptable for a blank template but not for project input.")
    for field in spec.numeric_fields:
        if field not in df.columns:
            continue
        values = pd.to_numeric(df[field], errors="coerce")
        if len(values) and values.isna().any():
            _fail(result, f"Field {field} contains non-numeric values.")
    for field in spec.time_fields:
        if field not in df.columns:
            continue
        times = pd.to_datetime(df[field], errors="coerce")
        if len(times) and times.isna().any():
            _fail(result, f"Field {field} contains unparseable timestamps.")
    if extra_checks is not None and df is not None:
        extra_checks(result, df)
    return result


def _check_rainfall(result: dict[str, Any], df: pd.DataFrame) -> None:
    if "rainfall_mm" in df.columns:
        values = pd.to_numeric(df["rainfall_mm"], errors="coerce")
        if values.notna().any() and (values.dropna() < 0).any():
            _fail(result, "rainfall_mm must be >= 0.")


def _check_subbasins(result: dict[str, Any], df: pd.DataFrame) -> None:
    checks = {
        "area_km2": "area_km2 must be > 0.",
        "cn": "cn must satisfy 0 < cn <= 100.",
        "initial_abstraction_ratio": "initial_abstraction_ratio should usually satisfy 0 <= value <= 1.",
        "lag_time_hr": "lag_time_hr must be >= 0.",
    }
    for field, message in checks.items():
        if field not in df.columns:
            continue
        values = pd.to_numeric(df[field], errors="coerce")
        valid = values.dropna()
        if field == "area_km2" and not valid.empty and (valid <= 0).any():
            _fail(result, message)
        elif field == "cn" and not valid.empty and ((valid <= 0) | (valid > 100)).any():
            _fail(result, message)
        elif field == "initial_abstraction_ratio" and not valid.empty and ((valid < 0) | (valid > 1)).any():
            _warn(result, message)
        elif field == "lag_time_hr" and not valid.empty and (valid < 0).any():
            _fail(result, message)


def _check_reaches(result: dict[str, Any], df: pd.DataFrame) -> None:
    for field in ("length_km", "muskingum_k_hr"):
        if field in df.columns:
            values = pd.to_numeric(df[field], errors="coerce").dropna()
            if not values.empty and (values <= 0).any():
                _fail(result, f"{field} must be > 0.")
    if "slope" in df.columns:
        values = pd.to_numeric(df["slope"], errors="coerce").dropna()
        if not values.empty and (values < 0).any():
            _fail(result, "slope must be >= 0.")
    if "muskingum_x" in df.columns:
        values = pd.to_numeric(df["muskingum_x"], errors="coerce").dropna()
        if not values.empty and ((values < 0) | (values > 0.5)).any():
            _fail(result, "muskingum_x must satisfy 0 <= X <= 0.5.")


def _check_observed(result: dict[str, Any], df: pd.DataFrame) -> None:
    if "flow_cms" in df.columns:
        values = pd.to_numeric(df["flow_cms"], errors="coerce").dropna()
        if not values.empty and (values < 0).any():
            _warn(result, "flow_cms contains negative values. Check datum, reversals, or missing-value coding.")


def _check_mapping(result: dict[str, Any], df: pd.DataFrame) -> None:
    if "scale_factor" in df.columns:
        values = pd.to_numeric(df["scale_factor"], errors="coerce").dropna()
        if not values.empty and (values < 0).any():
            _fail(result, "scale_factor must be >= 0.")


def validate_rainfall_template(path: str | Path) -> dict[str, Any]:
    return _validate_csv(path, get_data_template("rainfall"), _check_rainfall)


def validate_subbasins_template(path: str | Path) -> dict[str, Any]:
    return _validate_csv(path, get_data_template("subbasins"), _check_subbasins)


def validate_reaches_template(path: str | Path) -> dict[str, Any]:
    return _validate_csv(path, get_data_template("reaches"), _check_reaches)


def validate_observed_streamflow_template(path: str | Path) -> dict[str, Any]:
    return _validate_csv(path, get_data_template("observed_streamflow"), _check_observed)


def validate_swmm_inflow_mapping_template(path: str | Path) -> dict[str, Any]:
    return _validate_csv(path, get_data_template("swmm_inflow_mapping"), _check_mapping)


def validate_gee_basin_boundary_template(path: str | Path) -> dict[str, Any]:
    geojson_path = Path(path)
    result = _result("gee_basin_boundary", geojson_path)
    if not geojson_path.exists():
        return _fail(result, f"File not found: {geojson_path}")
    try:
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _fail(result, f"GeoJSON could not be parsed: {exc}")
    result["fields"] = sorted(data.keys()) if isinstance(data, dict) else []
    features = data.get("features", []) if isinstance(data, dict) else []
    result["rows"] = len(features) if isinstance(features, list) else 0
    geometries: list[dict[str, Any]] = []
    if data.get("type") == "FeatureCollection" and isinstance(features, list):
        geometries = [feature.get("geometry") for feature in features if isinstance(feature, dict)]
    elif data.get("type") == "Feature":
        geometries = [data.get("geometry")]
    elif data.get("type") in {"Polygon", "MultiPolygon"}:
        geometries = [data]
    else:
        _fail(result, "GeoJSON must be a FeatureCollection, Feature, Polygon, or MultiPolygon.")
    if not geometries:
        _fail(result, "GeoJSON does not contain any geometry.")
    for geometry in geometries:
        if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            _fail(result, "All basin geometries must be Polygon or MultiPolygon.")
            break
    return result


VALIDATORS: dict[str, Callable[[str | Path], dict[str, Any]]] = {
    "rainfall": validate_rainfall_template,
    "subbasins": validate_subbasins_template,
    "reaches": validate_reaches_template,
    "observed_streamflow": validate_observed_streamflow_template,
    "swmm_inflow_mapping": validate_swmm_inflow_mapping_template,
    "gee_basin_boundary": validate_gee_basin_boundary_template,
}


def _candidate_file(dataset_dir: Path, canonical: str, example: str, template: str) -> Path | None:
    for name in (canonical, example, template):
        path = dataset_dir / name
        if path.exists():
            return path
    return None


def validate_project_input_dataset(dataset_dir: str | Path) -> dict[str, Any]:
    root = Path(dataset_dir).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    file_map = {
        "rainfall": ("rainfall.csv", "rainfall_example.csv", "rainfall_template.csv", True),
        "subbasins": ("subbasins.csv", "subbasins_example.csv", "subbasins_template.csv", True),
        "reaches": ("reaches.csv", "reaches_example.csv", "reaches_template.csv", True),
        "observed_streamflow": (
            "observed_streamflow.csv",
            "observed_streamflow_example.csv",
            "observed_streamflow_template.csv",
            False,
        ),
        "swmm_inflow_mapping": (
            "swmm_inflow_mapping.csv",
            "swmm_inflow_mapping_example.csv",
            "swmm_inflow_mapping_template.csv",
            False,
        ),
        "gee_basin_boundary": (
            "basin_boundary.geojson",
            "gee_basin_boundary_example.geojson",
            "gee_basin_boundary_template.geojson",
            False,
        ),
    }
    for name, (canonical, example, template, required) in file_map.items():
        path = _candidate_file(root, canonical, example, template)
        if path is None:
            result = _result(name, root / canonical)
            if required:
                _fail(result, f"Required dataset file missing. Expected {canonical}.")
            else:
                result["status"] = "missing_optional"
                result["warnings"].append(f"Optional dataset file not found: {canonical}")
            checks.append(result)
            continue
        checks.append(VALIDATORS[name](path))
    status = "passed"
    if any(check["status"] == "failed" for check in checks):
        status = "failed"
    elif any(check["status"] in {"warning", "missing_optional"} for check in checks):
        status = "warning"
    return {"dataset_dir": str(root), "status": status, "checks": checks}


def _flatten_checks(validation: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for check in validation.get("checks", []):
        rows.append(
            {
                "template_name": check.get("template_name", ""),
                "path": check.get("path", ""),
                "status": check.get("status", ""),
                "rows": check.get("rows", 0),
                "fields": ", ".join(check.get("fields", [])),
                "errors": "; ".join(check.get("errors", [])),
                "warnings": "; ".join(check.get("warnings", [])),
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows."
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.fillna("").iterrows():
        values = [str(row[column]).replace("\n", " ") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_data_template_summary(output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    validation = validate_project_input_dataset(output)
    table = _flatten_checks(validation)
    md = output / "data_template_summary.md"
    xlsx = output / "data_template_summary.xlsx"
    lines = [
        "# HydroLite Data Template Summary",
        "",
        f"- Dataset directory: `{output}`",
        f"- Overall status: `{validation['status']}`",
        "",
        "## Available Templates",
        "",
        "| Template | Description | Required Fields |",
        "| --- | --- | --- |",
    ]
    for row in list_data_templates():
        lines.append(
            f"| {row['template_name']} | {row['description']} | {', '.join(row['required_fields']) or 'GeoJSON geometry'} |"
        )
    lines.extend(["", "## Validation Checks", ""])
    if table.empty:
        lines.append("No checks available.")
    else:
        lines.append(_markdown_table(table))
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pd.ExcelWriter(xlsx) as writer:
        pd.DataFrame(list_data_templates()).to_excel(writer, sheet_name="templates", index=False)
        table.to_excel(writer, sheet_name="checks", index=False)
    return {"md": md, "xlsx": xlsx}
