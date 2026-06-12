from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
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


def _bbox_area_km2(bbox: list[float] | None) -> float | None:
    if not bbox:
        return None
    minx, miny, maxx, maxy = bbox
    mean_lat = math.radians((miny + maxy) / 2.0)
    width_km = max(0.0, (maxx - minx) * 111.320 * math.cos(mean_lat))
    height_km = max(0.0, (maxy - miny) * 110.574)
    return width_km * height_km


def _metric_value(rows: list[dict[str, Any]], metric_group: str, metric: str) -> float | None:
    for row in rows:
        if row.get("metric_group") == metric_group and row.get("metric") == metric:
            value = row.get("value")
            if pd.isna(value):
                return None
            return float(value)
    return None


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
        count = int(collection.size().getInfo())
        if count == 0:
            return [
                {
                    "metric_group": "precipitation",
                    "status": "failed",
                    "metric": "basin_mean_total_precipitation",
                    "value": pd.NA,
                    "unit": "mm",
                    "error_message": f"No CHIRPS images found for {start} to {end}.",
                    "next_steps": "Set start_date/end_date in the GEE config to a period covered by CHIRPS.",
                }
            ]
        image = collection.select("precipitation").sum()
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=5500,
            maxPixels=1_000_000,
        ).getInfo()
        value = stats.get("precipitation")
        if value is None:
            return [
                {
                    "metric_group": "precipitation",
                    "status": "failed",
                    "metric": "basin_mean_total_precipitation",
                    "value": pd.NA,
                    "unit": "mm",
                    "error_message": f"CHIRPS returned no precipitation value for basin and date range {start} to {end}.",
                    "next_steps": "Check basin geometry, date range, and CHIRPS coverage.",
                }
            ]
        return [
            {
                "metric_group": "precipitation",
                "status": "available",
                "metric": "basin_mean_total_precipitation",
                "value": value,
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


def export_chirps_timeseries(config_path: str | Path) -> pd.DataFrame:
    config = _load_config(config_path)
    init = initialize_gee(project=config.get("project") or None)
    columns = ["datetime", "time", "subbasin_id", "rain_mm", "status", "error_message"]
    if init["status"] != "available":
        return pd.DataFrame(
            [
                {
                    "datetime": "",
                    "time": "",
                    "subbasin_id": "GEE_BASIN_1",
                    "rain_mm": pd.NA,
                    "status": init["status"],
                    "error_message": init.get("error_message", ""),
                }
            ],
            columns=columns,
        )
    try:
        import ee

        start, end = _date_range(config)
        geometry = _geometry_from_geojson(_basin_boundary(config))
        collection = (
            ee.ImageCollection(get_dataset_metadata("precipitation")["gee_id"])
            .filterDate(start, end)
            .select("precipitation")
        )
        count = int(collection.size().getInfo())
        if count == 0:
            return pd.DataFrame(
                [
                    {
                        "datetime": "",
                        "time": "",
                        "subbasin_id": "GEE_BASIN_1",
                        "rain_mm": pd.NA,
                        "status": "failed",
                        "error_message": f"No CHIRPS images found for {start} to {end}.",
                    }
                ],
                columns=columns,
            )

        def summarize_image(image):
            value = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=5500,
                maxPixels=1_000_000,
            ).get("precipitation")
            return ee.Feature(None, {"datetime": image.date().format("YYYY-MM-dd"), "rain_mm": value})

        features = collection.map(summarize_image).getInfo().get("features", [])
        rows = []
        for feature in features:
            props = feature.get("properties", {})
            value = props.get("rain_mm")
            if value is None:
                continue
            dt = str(props.get("datetime"))
            rows.append(
                {
                    "datetime": dt,
                    "time": f"{dt} 00:00",
                    "subbasin_id": "GEE_BASIN_1",
                    "rain_mm": float(value),
                    "status": "available",
                    "error_message": "",
                }
            )
        if not rows:
            rows.append(
                {
                    "datetime": "",
                    "time": "",
                    "subbasin_id": "GEE_BASIN_1",
                    "rain_mm": pd.NA,
                    "status": "failed",
                    "error_message": "CHIRPS returned no usable precipitation values for this basin.",
                }
            )
        return pd.DataFrame(rows, columns=columns)
    except Exception as exc:
        return pd.DataFrame(
            [
                {
                    "datetime": "",
                    "time": "",
                    "subbasin_id": "GEE_BASIN_1",
                    "rain_mm": pd.NA,
                    "status": "failed",
                    "error_message": str(exc),
                }
            ],
            columns=columns,
        )


def export_temperature_timeseries(config_path: str | Path) -> pd.DataFrame:
    config = _load_config(config_path)
    init = initialize_gee(project=config.get("project") or None)
    columns = ["datetime", "basin_id", "temperature_mean_c", "temperature_source", "status", "error_message"]
    metadata = get_dataset_metadata("temperature")
    source = metadata["gee_id"]
    if init["status"] != "available":
        return pd.DataFrame(
            [
                {
                    "datetime": "",
                    "basin_id": "GEE_BASIN_1",
                    "temperature_mean_c": pd.NA,
                    "temperature_source": source,
                    "status": init["status"],
                    "error_message": init.get("error_message", ""),
                }
            ],
            columns=columns,
        )
    try:
        import ee

        start, end = _date_range(config)
        geometry = _geometry_from_geojson(_basin_boundary(config))
        dataset_config = (config.get("datasets") or {}).get("temperature") or {}
        gee_id = dataset_config.get("gee_id") or source
        band = dataset_config.get("band") or metadata["bands"][0]
        collection = ee.ImageCollection(gee_id).filterDate(start, end).select(band)
        count = int(collection.size().getInfo())
        if count == 0:
            return pd.DataFrame(
                [
                    {
                        "datetime": "",
                        "basin_id": "GEE_BASIN_1",
                        "temperature_mean_c": pd.NA,
                        "temperature_source": gee_id,
                        "status": "failed",
                        "error_message": f"No ERA5-Land images found for {start} to {end}.",
                    }
                ],
                columns=columns,
            )

        def summarize_image(image):
            value_k = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=11_000,
                maxPixels=1_000_000,
            ).get(band)
            return ee.Feature(None, {"datetime": image.date().format("YYYY-MM-dd"), "temperature_mean_k": value_k})

        features = collection.map(summarize_image).getInfo().get("features", [])
        rows = []
        for feature in features:
            props = feature.get("properties", {})
            value_k = props.get("temperature_mean_k")
            if value_k is None:
                continue
            dt = str(props.get("datetime"))
            rows.append(
                {
                    "datetime": dt,
                    "basin_id": "GEE_BASIN_1",
                    "temperature_mean_c": float(value_k) - 273.15,
                    "temperature_source": gee_id,
                    "status": "available",
                    "error_message": "",
                }
            )
        if not rows:
            rows.append(
                {
                    "datetime": "",
                    "basin_id": "GEE_BASIN_1",
                    "temperature_mean_c": pd.NA,
                    "temperature_source": gee_id,
                    "status": "failed",
                    "error_message": "ERA5-Land returned no usable temperature values for this basin.",
                }
            )
        return pd.DataFrame(rows, columns=columns)
    except Exception as exc:
        return pd.DataFrame(
            [
                {
                    "datetime": "",
                    "basin_id": "GEE_BASIN_1",
                    "temperature_mean_c": pd.NA,
                    "temperature_source": source,
                    "status": "failed",
                    "error_message": str(exc),
                }
            ],
            columns=columns,
        )


def export_dem_summary(config_path: str | Path) -> pd.DataFrame:
    return pd.DataFrame(summarize_dem_over_basin(config_path))


def export_surface_water_summary(config_path: str | Path) -> pd.DataFrame:
    return pd.DataFrame(summarize_surface_water_over_basin(config_path))


def _basin_summary_rows(config_path: str | Path, rainfall: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = _load_config(config_path)
    boundary = _basin_boundary(config)
    bbox_info = get_boundary_bbox(boundary)
    bbox = bbox_info.get("bbox")
    metrics: list[dict[str, Any]] = []
    metrics.extend(summarize_dem_over_basin(config_path))
    metrics.extend(summarize_precipitation_over_basin(config_path))
    metrics.extend(summarize_surface_water_over_basin(config_path))
    start, end = _date_range(config)
    available_rain = rainfall[rainfall["status"] == "available"] if "status" in rainfall.columns else rainfall
    rain_values = pd.to_numeric(available_rain.get("rain_mm", pd.Series(dtype=float)), errors="coerce").dropna()
    total_rain = float(rain_values.sum()) if not rain_values.empty else _metric_value(
        metrics, "precipitation", "basin_mean_total_precipitation"
    )
    mean_daily = float(rain_values.mean()) if not rain_values.empty else None
    init = initialize_gee(project=config.get("project") or None)
    row = {
        "basin_boundary": str(boundary),
        "bbox": bbox,
        "area_km2": _bbox_area_km2(bbox),
        "dem_mean": _metric_value(metrics, "dem", "mean_elevation"),
        "dem_min": _metric_value(metrics, "dem", "min_elevation"),
        "dem_max": _metric_value(metrics, "dem", "max_elevation"),
        "surface_water_occurrence_mean": _metric_value(metrics, "surface_water", "mean_occurrence"),
        "surface_water_occurrence_max": _metric_value(metrics, "surface_water", "max_occurrence"),
        "precipitation_start_date": start,
        "precipitation_end_date": end,
        "precipitation_total_mm": total_rain,
        "precipitation_mean_daily_mm": mean_daily,
        "gee_project": init.get("project") or "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return row, metrics


def generate_hydrolite_parameter_suggestions(config_path: str | Path) -> dict[str, Any]:
    rainfall = export_chirps_timeseries(config_path)
    basin, metrics = _basin_summary_rows(config_path, rainfall)
    area = float(basin["area_km2"] or 1.0)
    dem_min = basin.get("dem_min")
    dem_max = basin.get("dem_max")
    relief = max(0.0, float(dem_max or 0.0) - float(dem_min or 0.0))
    water_occurrence = basin.get("surface_water_occurrence_mean")
    rain_total = basin.get("precipitation_total_mm") or 0.0
    cn = 75.0
    if water_occurrence is not None and float(water_occurrence) > 50:
        cn += 5.0
    if rain_total and float(rain_total) > 250:
        cn += 3.0
    cn = max(70.0, min(85.0, cn))
    lag = max(1.0, min(18.0, 1.5 + math.sqrt(area) * 1.6 - min(relief, 300.0) / 120.0))
    k_hours = max(15.0, lag * 1.5)
    x = 0.2
    return {
        "suggested_subbasin_id": "GEE_BASIN_1",
        "suggested_area_km2": area,
        "suggested_cn": round(cn, 2),
        "suggested_lag_hours": round(lag, 2),
        "suggested_muskingum_k_hours": round(k_hours, 2),
        "suggested_muskingum_x": x,
        "basis": (
            "Transparent heuristic using bbox-derived area, DEM relief, JRC water occurrence, "
            "and CHIRPS precipitation total."
        ),
        "warning": "Initial parameter suggestion only; not a calibrated hydrologic parameter set.",
        "source_status": "; ".join(f"{row.get('metric_group')}={row.get('status')}" for row in metrics),
    }


def generate_hydrolite_rainfall_csv(config_path: str | Path) -> pd.DataFrame:
    return export_chirps_timeseries(config_path)


def generate_gee_temperature_csv(config_path: str | Path) -> pd.DataFrame:
    return export_temperature_timeseries(config_path)


def _has_usable_numeric_rows(frame: pd.DataFrame, value_column: str) -> bool:
    if value_column not in frame.columns:
        return False
    if "status" in frame.columns and not (frame["status"] == "available").any():
        return False
    return pd.to_numeric(frame[value_column], errors="coerce").notna().any()


def _write_or_preserve_timeseries(frame: pd.DataFrame, path: Path, value_column: str) -> pd.DataFrame:
    if _has_usable_numeric_rows(frame, value_column) or not path.exists():
        frame.to_csv(path, index=False)
        return frame
    try:
        existing = pd.read_csv(path)
        if _has_usable_numeric_rows(existing, value_column):
            return existing
    except Exception:
        pass
    frame.to_csv(path, index=False)
    return frame


def _write_demo_gee_files(output_dir: Path, rainfall_path: Path, suggestions: dict[str, Any]) -> dict[str, Path] | None:
    rainfall = pd.read_csv(rainfall_path)
    usable = rainfall[rainfall["status"] == "available"] if "status" in rainfall.columns else rainfall
    usable = usable[pd.to_numeric(usable["rain_mm"], errors="coerce").notna()]
    if usable.empty:
        return None
    data_dir = PROJECT_ROOT / "data_demo" / "gee"
    data_dir.mkdir(parents=True, exist_ok=True)
    subbasins = data_dir / "gee_subbasins.csv"
    reaches = data_dir / "gee_reaches.csv"
    case_file = PROJECT_ROOT / "cases" / "demo_gee.yaml"
    pd.DataFrame(
        [
            {
                "id": suggestions["suggested_subbasin_id"],
                "area_km2": suggestions["suggested_area_km2"],
                "curve_number": suggestions["suggested_cn"],
                "lag_hours": suggestions["suggested_lag_hours"],
            }
        ]
    ).to_csv(subbasins, index=False)
    pd.DataFrame(
        [
            {
                "id": "GEE_R1",
                "from": "GEE_BASIN_1",
                "to": "outlet",
                "K_hours": suggestions["suggested_muskingum_k_hours"],
                "X": suggestions["suggested_muskingum_x"],
            }
        ]
    ).to_csv(reaches, index=False)
    case_file.write_text(
        yaml.safe_dump(
            {
                "name": "demo_gee",
                "model": {"time_step_hours": 24.0},
                "inputs": {
                    "directory": ".",
                    "rainfall": "output/gee/hydrolite_inputs/gee_chirps_rainfall.csv",
                    "subcatchments": "data_demo/gee/gee_subbasins.csv",
                    "reaches": "data_demo/gee/gee_reaches.csv",
                },
                "outputs": {"directory": "output/demo_gee"},
                "observed": {
                    "enabled": True,
                    "observed_streamflow_csv": "data_demo/observed/demo_observed_streamflow.csv",
                    "time_column": "datetime",
                    "flow_column": "observed_streamflow_m3s",
                    "gauge_id_column": "gauge_id",
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return {"subbasins": subbasins, "reaches": reaches, "case": case_file}


def write_hydrolite_gee_outputs(config_path: str | Path) -> dict[str, Path]:
    config = _load_config(config_path)
    root = _output_folder(config) / "hydrolite_inputs"
    root.mkdir(parents=True, exist_ok=True)
    basin_xlsx = root / "gee_basin_summary.xlsx"
    basin_csv = root / "gee_basin_summary.csv"
    rainfall_csv = root / "gee_chirps_rainfall.csv"
    temperature_csv = root / "gee_temperature_daily.csv"
    suggestions_xlsx = root / "gee_parameter_suggestions.xlsx"
    suggestions_yaml = root / "gee_parameter_suggestions.yaml"
    report_md = root / "gee_to_hydrolite_report.md"

    rainfall = _write_or_preserve_timeseries(generate_hydrolite_rainfall_csv(config_path), rainfall_csv, "rain_mm")
    temperature = _write_or_preserve_timeseries(
        generate_gee_temperature_csv(config_path), temperature_csv, "temperature_mean_c"
    )
    basin_row, _metrics = _basin_summary_rows(config_path, rainfall)
    basin = pd.DataFrame([basin_row])
    basin.to_excel(basin_xlsx, index=False)
    basin.to_csv(basin_csv, index=False)
    suggestions = generate_hydrolite_parameter_suggestions(config_path)
    pd.DataFrame([suggestions]).to_excel(suggestions_xlsx, index=False)
    suggestions_yaml.write_text(yaml.safe_dump(suggestions, sort_keys=False, allow_unicode=True), encoding="utf-8")
    demo_files = _write_demo_gee_files(root, rainfall_csv, suggestions)
    temperature_status_counts = temperature["status"].value_counts().to_dict() if "status" in temperature.columns else {}
    report_md.write_text(
        "\n".join(
            [
                "# GEE to HydroLite Input Report",
                "",
                f"Config: `{config_path}`",
                f"Basin summary: `{basin_xlsx}`",
                f"Rainfall CSV: `{rainfall_csv}`",
                f"Temperature CSV: `{temperature_csv}`",
                f"Parameter suggestions: `{suggestions_xlsx}`",
                "",
                "Temperature source: ERA5-Land daily 2 m air temperature when available.",
                "Temperature units: GEE Kelvin values are converted to Celsius in `temperature_mean_c`.",
                f"Temperature status counts: `{temperature_status_counts}`",
                "",
                "The suggested CN, lag time, and Muskingum parameters are transparent initial heuristics only.",
                "They are not calibrated model parameters and should be reviewed before decision use.",
                "",
                f"demo_gee.yaml generated: `{bool(demo_files)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    outputs = {
        "gee_basin_summary_xlsx": basin_xlsx,
        "gee_basin_summary_csv": basin_csv,
        "gee_chirps_rainfall_csv": rainfall_csv,
        "gee_temperature_daily_csv": temperature_csv,
        "gee_parameter_suggestions_xlsx": suggestions_xlsx,
        "gee_parameter_suggestions_yaml": suggestions_yaml,
        "gee_to_hydrolite_report_md": report_md,
    }
    if demo_files:
        outputs.update({f"demo_{key}": value for key, value in demo_files.items()})
    return outputs


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
