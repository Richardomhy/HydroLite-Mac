from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from hydrolite.gee.auth import initialize_gee
from hydrolite.gee.basin import get_boundary_bbox, read_geojson_boundary
from hydrolite.gee.datasets import get_dataset_metadata, list_supported_datasets


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve(path_value: str | Path | None, base: Path = PROJECT_ROOT) -> Path:
    path = Path(path_value or "").expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("GEE config root must be a mapping.")
    return data


def _output_folder(config: dict[str, Any]) -> Path:
    output_value = config.get("output_folder") or (config.get("export") or {}).get("output_folder") or "output/gee"
    folder = _resolve(output_value)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _basin_boundary(config: dict[str, Any]) -> Path:
    return _resolve(config.get("basin_boundary") or "data_demo/gee/demo_basin.geojson")


def _date_range(config: dict[str, Any]) -> tuple[str, str]:
    explicit_start = config.get("start_date") or (config.get("date_range") or {}).get("start_date")
    explicit_end = config.get("end_date") or (config.get("date_range") or {}).get("end_date")
    end = date.fromisoformat(str(explicit_end)) if explicit_end else date.today()
    start = date.fromisoformat(str(explicit_start)) if explicit_start else end - timedelta(days=30)
    return start.isoformat(), end.isoformat()


def _geometry_from_geojson(boundary_path: Path):
    import ee

    loaded = read_geojson_boundary(boundary_path)
    if loaded["status"] != "available":
        raise ValueError(loaded["error_message"])
    data = loaded["geojson"]
    if data["type"] == "FeatureCollection":
        geometry = data["features"][0]["geometry"]
    elif data["type"] == "Feature":
        geometry = data["geometry"]
    else:
        geometry = data
    return ee.Geometry(geometry)


def create_gee_data_plan(config_path: str | Path) -> pd.DataFrame:
    config = _load_config(config_path)
    boundary = _basin_boundary(config)
    bbox = get_boundary_bbox(boundary)
    rows = []
    for dataset_name in list_supported_datasets():
        metadata = get_dataset_metadata(dataset_name)
        rows.append(
            {
                "dataset_name": metadata["dataset_name"],
                "gee_id": metadata["gee_id"],
                "data_type": metadata["data_type"],
                "spatial_resolution": metadata["spatial_resolution"],
                "temporal_resolution": metadata["temporal_resolution"],
                "bands": ", ".join(metadata["bands"]),
                "basin_boundary": str(boundary),
                "bbox": bbox.get("bbox"),
                "status": "planned" if bbox["status"] == "available" else "boundary_unavailable",
                "notes": metadata["notes"],
            }
        )
    return pd.DataFrame(rows)


def _unavailable_summary(metric_group: str, init: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric_group": metric_group,
        "status": init["status"],
        "value": pd.NA,
        "unit": "",
        "error_message": init.get("error_message", ""),
        "next_steps": "; ".join(init.get("next_steps", [])),
    }


def summarize_dem_over_basin(config_path: str | Path) -> list[dict[str, Any]]:
    config = _load_config(config_path)
    init = initialize_gee(project=config.get("project") or None)
    if init["status"] != "available":
        return [_unavailable_summary("dem", init)]
    try:
        import ee

        geometry = _geometry_from_geojson(_basin_boundary(config))
        image = ee.Image(get_dataset_metadata("DEM")["gee_id"]).select("elevation")
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
            geometry=geometry,
            scale=int((config.get("export") or {}).get("scale", 30)),
            maxPixels=1_000_000,
        ).getInfo()
        return [
            {"metric_group": "dem", "status": "available", "metric": "mean_elevation", "value": stats.get("elevation_mean"), "unit": "m", "error_message": "", "next_steps": ""},
            {"metric_group": "dem", "status": "available", "metric": "min_elevation", "value": stats.get("elevation_min"), "unit": "m", "error_message": "", "next_steps": ""},
            {"metric_group": "dem", "status": "available", "metric": "max_elevation", "value": stats.get("elevation_max"), "unit": "m", "error_message": "", "next_steps": ""},
        ]
    except Exception as exc:
        return [{"metric_group": "dem", "status": "failed", "metric": "", "value": pd.NA, "unit": "", "error_message": str(exc), "next_steps": ""}]


def summarize_precipitation_over_basin(config_path: str | Path) -> list[dict[str, Any]]:
    config = _load_config(config_path)
    init = initialize_gee(project=config.get("project") or None)
    if init["status"] != "available":
        return [_unavailable_summary("precipitation", init)]
    try:
        import ee

        start, end = _date_range(config)
        geometry = _geometry_from_geojson(_basin_boundary(config))
        collection = ee.ImageCollection(get_dataset_metadata("precipitation")["gee_id"]).filterDate(start, end)
        image = collection.select("precipitation").sum()
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=5500,
            maxPixels=1_000_000,
        ).getInfo()
        return [
            {
                "metric_group": "precipitation",
                "status": "available",
                "metric": "basin_mean_total_precipitation",
                "value": stats.get("precipitation"),
                "unit": "mm",
                "error_message": "",
                "next_steps": "",
            }
        ]
    except Exception as exc:
        return [{"metric_group": "precipitation", "status": "failed", "metric": "", "value": pd.NA, "unit": "", "error_message": str(exc), "next_steps": ""}]


def summarize_surface_water_over_basin(config_path: str | Path) -> list[dict[str, Any]]:
    config = _load_config(config_path)
    init = initialize_gee(project=config.get("project") or None)
    if init["status"] != "available":
        return [_unavailable_summary("surface_water", init)]
    try:
        import ee

        geometry = _geometry_from_geojson(_basin_boundary(config))
        image = ee.Image(get_dataset_metadata("surface_water")["gee_id"]).select("occurrence")
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
            geometry=geometry,
            scale=30,
            maxPixels=1_000_000,
        ).getInfo()
        return [
            {"metric_group": "surface_water", "status": "available", "metric": "mean_occurrence", "value": stats.get("occurrence_mean"), "unit": "%", "error_message": "", "next_steps": ""},
            {"metric_group": "surface_water", "status": "available", "metric": "max_occurrence", "value": stats.get("occurrence_max"), "unit": "%", "error_message": "", "next_steps": ""},
        ]
    except Exception as exc:
        return [{"metric_group": "surface_water", "status": "failed", "metric": "", "value": pd.NA, "unit": "", "error_message": str(exc), "next_steps": ""}]


def write_gee_summary_outputs(config_path: str | Path) -> dict[str, Path]:
    config = _load_config(config_path)
    output = _output_folder(config)
    plan_path = output / "gee_data_plan.xlsx"
    summary_xlsx = output / "gee_summary.xlsx"
    summary_csv = output / "gee_summary.csv"
    report_md = output / "gee_report.md"

    plan = create_gee_data_plan(config_path)
    plan.to_excel(plan_path, index=False)
    rows = []
    rows.extend(summarize_dem_over_basin(config_path))
    rows.extend(summarize_precipitation_over_basin(config_path))
    rows.extend(summarize_surface_water_over_basin(config_path))
    summary = pd.DataFrame(rows)
    summary.to_excel(summary_xlsx, index=False)
    summary.to_csv(summary_csv, index=False)
    status_counts = summary["status"].value_counts().to_dict() if "status" in summary.columns else {}
    report_md.write_text(
        "\n".join(
            [
                "# GEE Data Center Summary",
                "",
                f"Config: `{config_path}`",
                f"Basin boundary: `{_basin_boundary(config)}`",
                f"Status counts: `{status_counts}`",
                "",
                "No secrets or credentials are written by this report.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "gee_data_plan": plan_path,
        "gee_summary_xlsx": summary_xlsx,
        "gee_summary_csv": summary_csv,
        "gee_report_md": report_md,
    }


def export_to_drive_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {"status": "placeholder", "message": "Drive export task submission is not enabled in this workflow."}


def export_to_local_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {"status": "placeholder", "message": "Local raster export is not enabled in this workflow."}


def write_gee_export_plan(path: str | Path, plan: dict[str, Any] | None = None) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = plan or {"status": "placeholder", "message": "Use create_gee_data_plan for tabular planning."}
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return output_path
