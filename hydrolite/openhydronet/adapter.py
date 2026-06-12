from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from hydrolite.openhydronet.config import load_openhydronet_config
from hydrolite.openhydronet.postprocess import build_input_quality_report, write_input_quality_report


def describe_openhydronet_adapter() -> dict[str, str]:
    return {
        "status": "input_adapter_ready",
        "purpose": "Map HydroLite, GEE, and observed gauge data into a future OpenHydroNet-style schema.",
    }


def map_hydrolite_to_openhydronet_schema_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {
        "status": "placeholder",
        "message": "HydroLite result_flow.csv to OpenHydroNet feature mapping is not implemented yet.",
    }


def map_gee_to_openhydronet_schema_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {
        "status": "placeholder",
        "message": "GEE static and meteorological features to OpenHydroNet schema mapping is not implemented yet.",
    }


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _first_row(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"Input file has no rows: {path}")
    return df.iloc[0].to_dict()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required YAML file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _json_default(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _detect_time_column(df: pd.DataFrame) -> str:
    for name in ("datetime", "time", "date", "timestamp"):
        if name in df.columns:
            return name
    for name in df.columns:
        if "time" in name.lower() or "date" in name.lower():
            return name
    raise ValueError("Could not identify a datetime column.")


def detect_streamflow_column(df: pd.DataFrame) -> str:
    candidates = [
        "streamflow_m3s",
        "outflow_cms",
        "outlet_flow",
        "flow_cms",
        "reach_GEE_R1_outflow_cms",
        "inflow_cms",
    ]
    for name in candidates:
        if name in df.columns:
            return name
    flow_like = [name for name in df.columns if "flow" in name.lower() and pd.api.types.is_numeric_dtype(df[name])]
    if flow_like:
        outflow_like = [name for name in flow_like if "out" in name.lower()]
        return outflow_like[0] if outflow_like else flow_like[-1]
    numeric = [name for name in df.columns if pd.api.types.is_numeric_dtype(df[name])]
    if numeric:
        return numeric[-1]
    raise ValueError("Could not identify a streamflow column in HydroLite result_flow.csv.")


def _static_attributes(adapter: dict[str, Any], basin_row: dict[str, Any], suggestions: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "basin_id": adapter["basin_id"],
                "gauge_id": adapter["gauge_id"],
                "area_km2": basin_row.get("area_km2") or suggestions.get("suggested_area_km2"),
                "dem_mean": basin_row.get("dem_mean"),
                "dem_min": basin_row.get("dem_min"),
                "dem_max": basin_row.get("dem_max"),
                "surface_water_occurrence_mean": basin_row.get("surface_water_occurrence_mean"),
                "suggested_cn": suggestions.get("suggested_cn"),
                "suggested_lag_hours": suggestions.get("suggested_lag_hours"),
                "suggested_muskingum_k_hours": suggestions.get("suggested_muskingum_k_hours"),
                "suggested_muskingum_x": suggestions.get("suggested_muskingum_x"),
                "source": "GEE HydroLite input products",
            }
        ]
    )


def _meteorological_forcing(adapter: dict[str, Any]) -> pd.DataFrame:
    rainfall_path = _resolve_path(adapter["gee_rainfall_csv"])
    rainfall = pd.read_csv(rainfall_path)
    time_col = _detect_time_column(rainfall)
    rain_col = "rain_mm" if "rain_mm" in rainfall.columns else "rainfall" if "rainfall" in rainfall.columns else ""
    if not rain_col:
        raise ValueError(f"Could not identify rainfall column in {rainfall_path}")
    met = pd.DataFrame(
        {
            "datetime": pd.to_datetime(rainfall[time_col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
            "basin_id": adapter["basin_id"],
            "precipitation_mm": pd.to_numeric(rainfall[rain_col], errors="coerce"),
        }
    )
    temperature_path = _resolve_path(adapter.get("gee_temperature_csv") or "output/gee/hydrolite_inputs/gee_temperature_daily.csv")
    if not temperature_path.exists():
        met["temperature_mean_c"] = pd.NA
        met["temperature_source"] = ""
        met["temperature_status"] = "missing_temperature_file"
        return met
    temperature = pd.read_csv(temperature_path)
    temp_time_col = _detect_time_column(temperature)
    temp_values = (
        pd.to_numeric(temperature["temperature_mean_c"], errors="coerce")
        if "temperature_mean_c" in temperature.columns
        else pd.Series([pd.NA] * len(temperature))
    )
    temp_source = temperature["temperature_source"] if "temperature_source" in temperature.columns else pd.Series([""] * len(temperature))
    temp_status = temperature["status"] if "status" in temperature.columns else pd.Series([""] * len(temperature))
    temp_basin = temperature["basin_id"] if "basin_id" in temperature.columns else pd.Series([adapter["basin_id"]] * len(temperature))
    temp = pd.DataFrame(
        {
            "datetime": pd.to_datetime(temperature[temp_time_col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
            "basin_id": temp_basin,
            "temperature_mean_c": temp_values,
            "temperature_source": temp_source,
            "temperature_status": temp_status,
        }
    )
    temp["basin_id"] = temp["basin_id"].fillna(adapter["basin_id"]).astype(str)
    merged = met.merge(temp, on=["datetime", "basin_id"], how="left")
    if "temperature_mean_c" not in merged.columns:
        merged["temperature_mean_c"] = pd.NA
    return merged


def _hydrolite_streamflow(adapter: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    flow_path = _resolve_path(adapter["hydrolite_result_flow"])
    result = pd.read_csv(flow_path)
    time_col = _detect_time_column(result)
    flow_col = detect_streamflow_column(result)
    frame = pd.DataFrame(
        {
            "datetime": pd.to_datetime(result[time_col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
            "basin_id": adapter["basin_id"],
            "streamflow_m3s": pd.to_numeric(result[flow_col], errors="coerce"),
            "source_case": "demo_gee",
        }
    )
    return frame, flow_col


def prepare_openhydronet_inputs(config_path: str | Path) -> dict[str, Any]:
    config = load_openhydronet_config(config_path)
    adapter = config.get("input_adapter") or {}
    if not adapter.get("enabled", False):
        raise ValueError("input_adapter.enabled must be true to prepare OpenHydroNet inputs.")
    required = [
        "basin_id",
        "gauge_id",
        "gee_basin_summary",
        "gee_rainfall_csv",
        "gee_parameter_suggestions",
        "hydrolite_result_flow",
        "output_folder",
    ]
    missing = [key for key in required if not adapter.get(key)]
    if missing:
        raise ValueError(f"Missing input_adapter keys: {missing}")

    output_dir = _resolve_path(adapter["output_folder"])
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    source_files = {
        "gee_basin_summary": str(_resolve_path(adapter["gee_basin_summary"])),
        "gee_rainfall_csv": str(_resolve_path(adapter["gee_rainfall_csv"])),
        "gee_temperature_csv": str(_resolve_path(adapter.get("gee_temperature_csv") or "output/gee/hydrolite_inputs/gee_temperature_daily.csv")),
        "gee_parameter_suggestions": str(_resolve_path(adapter["gee_parameter_suggestions"])),
        "hydrolite_result_flow": str(_resolve_path(adapter["hydrolite_result_flow"])),
        "basin_boundary": str(_resolve_path(adapter.get("basin_boundary", ""))) if adapter.get("basin_boundary") else "",
    }

    basin_row = _first_row(_resolve_path(adapter["gee_basin_summary"]))
    suggestions = _load_yaml(_resolve_path(adapter["gee_parameter_suggestions"]))
    static = _static_attributes(adapter, basin_row, suggestions)
    met = _meteorological_forcing(adapter)
    streamflow, detected_flow_col = _hydrolite_streamflow(adapter)
    temperature_values = pd.to_numeric(met.get("temperature_mean_c"), errors="coerce")
    temperature_coverage = float(temperature_values.notna().mean()) if len(met) else 0.0
    temperature_source = ""
    if "temperature_source" in met.columns:
        sources = [str(value) for value in met["temperature_source"].dropna().unique() if str(value)]
        temperature_source = sources[0] if sources else ""

    static_path = output_dir / "static_attributes.csv"
    met_path = output_dir / "meteorological_forcing.csv"
    flow_path = output_dir / "hydrolite_streamflow.csv"
    metadata_path = output_dir / "basin_metadata.json"
    manifest_path = output_dir / "input_manifest.json"
    quality_path = output_dir / "input_quality_report.xlsx"
    report_path = output_dir / "openhydronet_input_report.md"

    static.to_csv(static_path, index=False)
    met.to_csv(met_path, index=False)
    streamflow.to_csv(flow_path, index=False)

    observed_streamflow = _resolve_path(config.get("input", {}).get("observed_streamflow", ""))
    observed_exists = bool(str(observed_streamflow)) and observed_streamflow.exists()
    quality = build_input_quality_report(static, met, streamflow, observed_exists)
    write_input_quality_report(quality_path, quality)
    warning_rows = quality["warnings"].to_dict(orient="records")

    metadata = {
        "basin_id": adapter["basin_id"],
        "gauge_id": adapter["gauge_id"],
        "basin_boundary": source_files["basin_boundary"],
        "gee_project": basin_row.get("gee_project", ""),
        "generated_at": generated_at,
        "data_sources": source_files,
        "notes": [
            "This package is OpenHydroNet-ready input scaffolding, not calibrated AI training data.",
            "temperature_mean_c is sourced from GEE ERA5-Land daily temperature when available.",
            "temperature_mean_c is Celsius; GEE ERA5-Land Kelvin values are converted before packaging.",
            f"temperature coverage: {temperature_coverage:.1%}",
            f"HydroLite streamflow column detected from result_flow.csv: {detected_flow_col}",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")

    files = {
        "static_attributes": str(static_path),
        "meteorological_forcing": str(met_path),
        "hydrolite_streamflow": str(flow_path),
        "basin_metadata": str(metadata_path),
        "input_manifest": str(manifest_path),
        "input_quality_report": str(quality_path),
        "openhydronet_input_report": str(report_path),
    }
    manifest = {
        "package_version": "0.1",
        "generated_at": generated_at,
        "files": files,
        "source_files": source_files,
        "temperature": {
            "source": temperature_source,
            "unit": "Celsius",
            "non_null_ratio": temperature_coverage,
            "min": None if temperature_values.dropna().empty else float(temperature_values.min()),
            "mean": None if temperature_values.dropna().empty else float(temperature_values.mean()),
            "max": None if temperature_values.dropna().empty else float(temperature_values.max()),
        },
        "row_counts": {
            "static_attributes": int(len(static)),
            "meteorological_forcing": int(len(met)),
            "hydrolite_streamflow": int(len(streamflow)),
        },
        "warnings": warning_rows,
        "next_steps": [
            "Add observed streamflow for training/evaluation.",
            "Add additional meteorological forcings required by the target OpenHydroNet schema.",
            "Validate the package against the real OpenHydroNet repository schema before training or inference.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")

    report_path.write_text(
        "\n".join(
            [
                "# OpenHydroNet Input Package Report",
                "",
                "## 输入包概况",
                f"- basin_id: `{adapter['basin_id']}`",
                f"- gauge_id: `{adapter['gauge_id']}`",
                f"- output folder: `{output_dir}`",
                "",
                "## 数据来源",
                *[f"- {key}: `{value}`" for key, value in source_files.items() if value],
                f"- temperature source: `{temperature_source or 'unavailable'}`",
                "",
                "## 字段说明",
                "- `static_attributes.csv`: 流域静态属性与 GEE 参数建议。",
                "- `meteorological_forcing.csv`: CHIRPS 降雨与 ERA5-Land 2 m 日均温度。",
                "- `hydrolite_streamflow.csv`: HydroLite `demo_gee` 模拟出口流量。",
                "",
                "## 质量检查结果",
                f"- warnings: {len(warning_rows)}",
                *[f"- WARNING: {row['message']}" for row in warning_rows],
                f"- temperature non-null ratio: `{temperature_coverage:.2%}`",
                "- temperature unit: Celsius; ERA5-Land Kelvin values are converted by subtracting 273.15.",
                "",
                "## 已知限制",
                "- 当前输入包不是正式 OpenHydroNet 训练数据。",
                "- 缺少真实观测流量和真实模型 schema 校验。",
                f"- HydroLite 出口流量列自动识别为 `{detected_flow_col}`。",
                "- temperature_mean_c 单位为摄氏度；GEE ERA5-Land Kelvin 原始值已转换为 Celsius。",
                "",
                "## 后续真实推理/训练所需补充数据",
                "- 真实观测流量与质量控制标识。",
                "- 完整气象强迫变量。",
                "- OpenHydroNet 官方 schema 映射与归一化参数。",
                "- 模型 checkpoint 与严格的数据版本记录。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "status": "prepared",
        "output_dir": output_dir,
        "files": {**files, "input_manifest": str(manifest_path)},
        "quality": quality,
        "warnings": warning_rows,
        "detected_streamflow_column": detected_flow_col,
    }
