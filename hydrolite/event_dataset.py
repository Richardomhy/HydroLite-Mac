from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd
import yaml


def _time_column(frame: pd.DataFrame) -> str:
    return next((name for name in ("timestamp", "datetime", "time") if name in frame), "timestamp")


def _read_optional(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def load_event_source(workspace_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(workspace_dir)
    return {
        "events": _read_optional(root / "events.csv"),
        "rainfall": _read_optional(root / "rainfall.csv"),
        "flow": _read_optional(root / "streamflow.csv"),
        "stage": _read_optional(root / "stage.csv"),
        "reservoir": _read_optional(root / "reservoir_operation_observations.csv"),
        "meteorology": _read_optional(root / "meteorology.csv"),
        "stations": _read_optional(root / "station_metadata.csv"),
        "assimilation": _read_optional(root / "assimilation_observations.csv"),
    }


def align_event_timeseries(event_data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for name, frame in event_data.items():
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            output[name] = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
            continue
        time_col = _time_column(frame)
        work = frame.copy()
        work[time_col] = pd.to_datetime(work[time_col], errors="coerce", utc=True)
        work = work.dropna(subset=[time_col]).sort_values(time_col).drop_duplicates([time_col, *(["station_id"] if "station_id" in work else [])], keep="last")
        work = work.rename(columns={time_col: "timestamp"})
        output[name] = work.reset_index(drop=True)
    return output


def _resample(data: pd.DataFrame, interval: str, value_names: tuple[str, ...], how: str) -> pd.DataFrame:
    if data.empty:
        return data.copy()
    time_col = _time_column(data)
    value_col = next((name for name in value_names if name in data), None)
    if value_col is None:
        raise ValueError(f"Missing value column; expected one of {value_names}.")
    work = data.copy()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce", utc=True)
    groups = ["station_id"] if "station_id" in work else []
    pieces = []
    for keys, group in work.groupby(groups, dropna=False) if groups else [(None, work)]:
        series = pd.to_numeric(group.set_index(time_col)[value_col], errors="coerce")
        values = series.resample(interval).sum(min_count=1) if how == "sum" else series.resample(interval).mean()
        part = values.rename(value_col).reset_index().rename(columns={time_col: "timestamp"})
        if groups:
            part["station_id"] = keys
        pieces.append(part)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def resample_event_rainfall(data: pd.DataFrame, interval: str) -> pd.DataFrame:
    # Incremental rainfall is summed. Cumulative gauges must be differenced before this function.
    return _resample(data, interval, ("rainfall_mm", "rain_mm", "precipitation_mm"), "sum")


def resample_event_flow(data: pd.DataFrame, interval: str) -> pd.DataFrame:
    return _resample(data, interval, ("flow_cms", "observed_streamflow_m3s", "outflow_cms"), "mean")


def resample_event_stage(data: pd.DataFrame, interval: str) -> pd.DataFrame:
    return _resample(data, interval, ("stage_m", "water_level_m"), "mean")


def calculate_event_initial_conditions(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    flow = data.get("flow", pd.DataFrame())
    stage = data.get("stage", pd.DataFrame())
    rainfall = data.get("rainfall", pd.DataFrame())
    flow_col = next((name for name in ("flow_cms", "observed_streamflow_m3s") if name in flow), None)
    stage_col = next((name for name in ("stage_m", "water_level_m") if name in stage), None)
    rain_col = next((name for name in ("rainfall_mm", "rain_mm", "precipitation_mm") if name in rainfall), None)
    return {
        "initial_baseflow_cms": float(pd.to_numeric(flow[flow_col], errors="coerce").dropna().head(3).median()) if flow_col and not flow.empty else None,
        "initial_stage_m": float(pd.to_numeric(stage[stage_col], errors="coerce").dropna().head(3).median()) if stage_col and not stage.empty else None,
        "antecedent_precipitation_mm": float(pd.to_numeric(rainfall[rain_col], errors="coerce").head(24).sum()) if rain_col and not rainfall.empty else None,
        "method": "observed_window" if flow_col or stage_col else "missing",
        "source": "observed" if flow_col or stage_col else "unavailable",
        "uncertainty": "exploratory",
    }


def calculate_event_warmup_state(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    initial = calculate_event_initial_conditions(data)
    api = float(initial.get("antecedent_precipitation_mm") or 0)
    initial["soil_moisture_proxy"] = min(1.0, max(0.0, api / 100.0))
    initial["initial_reach_flow_cms"] = initial.get("initial_baseflow_cms")
    return initial


def build_event_dataset(event: dict[str, Any], workspace_dir: str | Path) -> dict[str, Any]:
    source = load_event_source(workspace_dir)
    event_id = str(event["event_id"])
    data: dict[str, pd.DataFrame] = {}
    for key in ("rainfall", "flow", "stage", "reservoir", "meteorology", "assimilation"):
        frame = source[key]
        data[key] = frame[frame["event_id"].astype(str) == event_id].copy() if not frame.empty and "event_id" in frame else frame.copy()
    data = align_event_timeseries(data)
    result = {
        "event": dict(event),
        **data,
        "initial_conditions": calculate_event_warmup_state(data),
        "synthetic_demo": bool(event.get("observed_is_synthetic", False)),
    }
    result["validation"] = validate_event_dataset(result)
    return result


def validate_event_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    errors, warnings = [], []
    for name in ("rainfall", "flow"):
        frame = dataset.get(name, pd.DataFrame())
        if frame.empty:
            errors.append(f"{name} is missing")
        elif "timestamp" not in frame:
            errors.append(f"{name} timestamp is missing")
    if dataset.get("synthetic_demo"):
        warnings.append("Synthetic demo event; cannot establish real-data validation.")
    return {"status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings}


def write_event_dataset(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    mapping = {
        "rainfall": "rainfall.csv", "flow": "flow_observed.csv", "stage": "stage_observed.csv",
        "reservoir": "reservoir_observed.csv", "meteorology": "meteorology.csv",
    }
    paths: dict[str, Path] = {}
    for key, name in mapping.items():
        frame = result.get(key, pd.DataFrame())
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            path = output / name
            frame.to_csv(path, index=False)
            paths[key] = path
    quality = []
    for name, frame in result.items():
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            quality.append({"dataset": name, "rows": len(frame), "missing_cells": int(frame.isna().sum().sum())})
    quality_path = output / "quality_flags.csv"
    pd.DataFrame(quality).to_csv(quality_path, index=False)
    initial_path = output / "initial_conditions.yaml"
    initial_path.write_text(yaml.safe_dump(result.get("initial_conditions", {}), sort_keys=False), encoding="utf-8")
    manifest = {
        "event_id": result["event"]["event_id"],
        "synthetic_demo": bool(result.get("synthetic_demo")),
        "validation": result["validation"],
        "files": {key: path.name for key, path in paths.items()},
    }
    manifest_path = output / "event_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**paths, "quality_flags": quality_path, "initial_conditions": initial_path, "manifest": manifest_path}
