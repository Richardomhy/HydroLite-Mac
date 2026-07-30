from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


RAINFALL_COLUMNS = [
    "issue_time", "valid_time", "lead_time_hr", "member_id", "subbasin_id",
    "precipitation_mm", "interval_minutes", "source", "scenario_type", "units", "quality_status",
]
CONTEXT_COLUMNS = [
    "timestamp", "outlet_flow_cms", "reservoir_stage_m", "reservoir_storage_m3",
    "antecedent_precipitation_mm", "soil_moisture_proxy", "baseflow_cms", "source", "quality_status",
]
SOURCE_TYPES = {"observed", "forecast", "scenario", "synthetic", "model_generated"}


def validate_forecast_issue_time(value: Any) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="raise")
    if pd.isna(timestamp):
        raise ValueError("issue_time is required")
    return timestamp


def validate_forecast_horizon(value: Any) -> float:
    horizon = float(value)
    if horizon <= 0:
        raise ValueError("forecast horizon must be positive")
    return horizon


def validate_rainfall_forecast_frame(data: pd.DataFrame) -> dict[str, Any]:
    missing = sorted(set(RAINFALL_COLUMNS) - set(data.columns))
    errors: list[str] = []
    if missing:
        errors.append(f"missing columns: {missing}")
    else:
        valid = pd.to_datetime(data["valid_time"], errors="coerce")
        if valid.isna().any():
            errors.append("valid_time contains unparseable values")
        if pd.to_numeric(data["precipitation_mm"], errors="coerce").isna().any():
            errors.append("precipitation_mm contains non-numeric values")
        elif (pd.to_numeric(data["precipitation_mm"]) < 0).any():
            errors.append("precipitation_mm must be nonnegative")
        if (pd.to_numeric(data["interval_minutes"], errors="coerce") <= 0).any():
            errors.append("interval_minutes must be positive")
        if not set(data["source"].astype(str)).issubset(SOURCE_TYPES):
            errors.append("source must use the forecast contract vocabulary")
        for _, group in data.groupby(["member_id", "subbasin_id"], dropna=False):
            delta = pd.to_datetime(group["valid_time"]).sort_values().diff().dropna().dt.total_seconds()
            if not delta.empty and delta.nunique() != 1:
                errors.append("irregular valid_time interval")
                break
    return {"status": "passed" if not errors else "failed", "errors": errors, "missing": missing}


def validate_flow_context_frame(data: pd.DataFrame) -> dict[str, Any]:
    required = {"timestamp", "outlet_flow_cms", "source", "quality_status"}
    missing = sorted(required - set(data.columns))
    return {"status": "passed" if not missing else "failed", "missing": missing}


def validate_reservoir_context_frame(data: pd.DataFrame) -> dict[str, Any]:
    required = {"timestamp", "reservoir_stage_m", "reservoir_storage_m3", "source", "quality_status"}
    missing = sorted(required - set(data.columns))
    return {"status": "passed" if not missing else "failed", "missing": missing}


def normalize_rainfall_forecast(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    aliases = {"time": "valid_time", "datetime": "valid_time", "rain_mm": "precipitation_mm"}
    frame = frame.rename(columns={key: value for key, value in aliases.items() if key in frame and value not in frame})
    frame["valid_time"] = pd.to_datetime(frame["valid_time"])
    issue = pd.to_datetime(frame["issue_time"].iloc[0]) if "issue_time" in frame else frame["valid_time"].min()
    frame["issue_time"] = pd.to_datetime(frame.get("issue_time", issue))
    frame["lead_time_hr"] = (frame["valid_time"] - frame["issue_time"]).dt.total_seconds() / 3600
    defaults = {
        "member_id": "baseline", "subbasin_id": "ALL", "interval_minutes": 60,
        "source": "scenario", "scenario_type": "observed_replay", "units": "mm",
        "quality_status": "synthetic_demo",
    }
    for column, value in defaults.items():
        if column not in frame:
            frame[column] = value
    frame["precipitation_mm"] = pd.to_numeric(frame["precipitation_mm"], errors="raise")
    frame = frame[RAINFALL_COLUMNS].sort_values(["member_id", "subbasin_id", "valid_time"]).reset_index(drop=True)
    check = validate_rainfall_forecast_frame(frame)
    if check["status"] != "passed":
        raise ValueError("; ".join(check["errors"]))
    return frame


def normalize_forecast_context(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy().rename(columns={"datetime": "timestamp", "time": "timestamp"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    for column in CONTEXT_COLUMNS:
        if column not in frame:
            frame[column] = "synthetic_demo" if column == "quality_status" else ("synthetic" if column == "source" else pd.NA)
    return frame[CONTEXT_COLUMNS]


def write_forecast_input_manifest(output_dir: str | Path, result: dict[str, Any]) -> Path:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "forecast_input_manifest.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
