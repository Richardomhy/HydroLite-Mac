"""Observation normalization and quality control for the method lab."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from hydrolite.water_quality_contracts import NON_DETECT_METHODS, default_variable_specs


ALIASES = {
    "parameter": "variable_id", "variable": "variable_id", "pollutant": "variable_id",
    "concentration_mg_l": "value", "concentration": "value", "result": "value",
    "date": "timestamp", "site_id": "station_id", "quality_flag": "quality_status",
}


def normalize_observation_columns(data: Any) -> pd.DataFrame:
    frame = pd.DataFrame(data).copy().rename(columns={key: value for key, value in ALIASES.items() if key in pd.DataFrame(data).columns})
    required = {"timestamp", "station_id", "variable_id", "value"}
    missing = sorted(required - set(frame))
    if missing:
        raise ValueError(f"Water-quality observations missing columns: {', '.join(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["station_id"] = frame["station_id"].astype("string")
    frame["variable_id"] = frame["variable_id"].astype("string")
    frame["raw_value"] = frame["value"]
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    if "unit" not in frame:
        frame["unit"] = "mg/L"
    if "qualifier" not in frame:
        frame["qualifier"] = ""
    if "source" not in frame:
        frame["source"] = "user"
    return frame


def apply_non_detect_policy(data: Any, method: str = "preserve_qualifier", detection_limits: Mapping[str, float] | None = None) -> pd.DataFrame:
    if method not in NON_DETECT_METHODS:
        raise ValueError(f"Unsupported non-detect method: {method}")
    frame = pd.DataFrame(data).copy()
    limits = dict(detection_limits or {})
    qualifier = frame.get("qualifier", pd.Series("", index=frame.index)).fillna("").astype(str).str.lower()
    non_detect = qualifier.str.contains(r"below|<|non.?detect", regex=True)
    frame["non_detect_method"] = method
    frame["below_detection_limit"] = non_detect
    dl = frame.get("detection_limit", pd.Series(np.nan, index=frame.index)).copy()
    if "variable_id" in frame:
        fallback = frame["variable_id"].map(limits)
        dl = pd.to_numeric(dl, errors="coerce").fillna(fallback)
    if method == "half_detection_limit":
        frame.loc[non_detect, "value"] = dl[non_detect] / 2.0
    elif method == "detection_limit":
        frame.loc[non_detect, "value"] = dl[non_detect]
    elif method == "missing":
        frame.loc[non_detect, "value"] = np.nan
    return frame


def run_observation_qc(data: Any, variable_specs: Mapping[str, Any] | None = None, *, non_detect_method: str = "preserve_qualifier", stale_days: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    specs = dict(variable_specs or default_variable_specs())
    frame = normalize_observation_columns(data)
    detection_limits = {key: value.detection_limit for key, value in specs.items() if value.detection_limit is not None}
    frame = apply_non_detect_policy(frame, non_detect_method, detection_limits)
    duplicate = frame.duplicated(["timestamp", "station_id", "variable_id"], keep=False)
    statuses: list[str] = []
    messages: list[str] = []
    for idx, row in frame.iterrows():
        status, message = "valid", ""
        spec = specs.get(str(row.variable_id))
        if pd.isna(row.timestamp) or not str(row.station_id).strip() or not str(row.variable_id).strip():
            status, message = "invalid", "missing identifier or invalid timestamp"
        elif str(row.unit) != (spec.canonical_unit if spec else "mg/L"):
            status, message = "unit_error", f"expected {spec.canonical_unit if spec else 'mg/L'}"
        elif pd.isna(row.value):
            status, message = ("below_detection_limit", "non-detect preserved") if bool(row.below_detection_limit) else ("missing", "value missing")
        elif spec and spec.nonnegative and float(row.value) < 0:
            status, message = "invalid", "negative concentration"
        elif spec:
            lower, upper = spec.valid_range
            if (lower is not None and row.value < lower) or (upper is not None and row.value > upper):
                status, message = "range_warning", "outside diagnostic valid range"
        if duplicate.iloc[idx] and status == "valid":
            status, message = "duplicate", "duplicate station-variable-timestamp"
        statuses.append(status); messages.append(message)
    frame["quality_status"] = statuses
    frame["quality_message"] = messages
    frame["training_eligible"] = ~frame.quality_status.isin(["invalid", "missing", "unit_error", "duplicate"])
    summary = frame.groupby(["variable_id", "quality_status"], dropna=False).size().reset_index(name="count")
    return frame, summary


def build_station_coverage(qc: Any) -> pd.DataFrame:
    frame = pd.DataFrame(qc).copy()
    return frame.groupby(["station_id", "variable_id"], as_index=False).agg(
        start_time=("timestamp", "min"), end_time=("timestamp", "max"), observations=("value", "count"),
        valid_for_training=("training_eligible", "sum"), missing_values=("value", lambda value: int(value.isna().sum())),
    )


def validate_observations(data: Any) -> dict[str, Any]:
    try:
        qc, summary = run_observation_qc(data)
    except (ValueError, TypeError) as exc:
        return {"status": "failed", "errors": [str(exc)], "warnings": []}
    invalid = int((~qc.training_eligible).sum())
    return {"status": "passed" if qc.training_eligible.any() else "failed", "errors": [] if qc.training_eligible.any() else ["no training-eligible observations"], "warnings": [f"{invalid} rows excluded from training"] if invalid else [], "quality_counts": summary.to_dict(orient="records")}


# Stable public API names used by future UI and project workflows.
normalize_water_quality_table = normalize_observation_columns


def validate_water_quality_units(data: Any, variable_specs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    qc, _ = run_observation_qc(data, variable_specs)
    rows = qc[qc.quality_status == "unit_error"]
    return {"status": "passed" if rows.empty else "failed", "unit_error_rows": rows.index.tolist()}


def validate_water_quality_timestamps(data: Any) -> dict[str, Any]:
    frame = normalize_observation_columns(data); invalid = frame.index[frame.timestamp.isna()].tolist()
    return {"status": "passed" if not invalid else "failed", "invalid_rows": invalid}


def detect_duplicate_observations(data: Any) -> pd.DataFrame:
    frame = normalize_observation_columns(data); return frame[frame.duplicated(["timestamp", "station_id", "variable_id"], keep=False)]


def detect_negative_concentrations(data: Any) -> pd.DataFrame:
    frame = normalize_observation_columns(data); return frame[frame.value < 0]


def detect_detection_limit_records(data: Any) -> pd.DataFrame:
    frame = normalize_observation_columns(data); qualifier = frame.qualifier.fillna("").astype(str).str.lower(); return frame[qualifier.str.contains(r"below|<|non.?detect", regex=True)]


def detect_extreme_values(data: Any, variable_specs: Mapping[str, Any] | None = None) -> pd.DataFrame:
    qc, _ = run_observation_qc(data, variable_specs); return qc[qc.quality_status == "range_warning"]


def detect_stale_station(data: Any, stale_days: int = 60, reference_time: Any | None = None) -> pd.DataFrame:
    frame = normalize_observation_columns(data); reference = pd.Timestamp(reference_time) if reference_time is not None else frame.timestamp.max(); latest = frame.groupby("station_id", as_index=False).timestamp.max(); latest["stale_days"] = (reference - latest.timestamp).dt.days; latest["quality_status"] = np.where(latest.stale_days > stale_days, "stale", "valid"); return latest


calculate_station_coverage = build_station_coverage


def calculate_variable_coverage(data: Any) -> pd.DataFrame:
    frame = normalize_observation_columns(data); return frame.groupby("variable_id", as_index=False).agg(start_time=("timestamp", "min"), end_time=("timestamp", "max"), observation_count=("value", "count"), station_count=("station_id", "nunique"))


def calculate_sampling_interval(data: Any) -> pd.DataFrame:
    frame = normalize_observation_columns(data).sort_values(["station_id", "variable_id", "timestamp"]); frame["interval_hours"] = frame.groupby(["station_id", "variable_id"]).timestamp.diff().dt.total_seconds() / 3600; return frame.groupby(["station_id", "variable_id"], as_index=False).interval_hours.median()


def classify_water_quality_readiness(data: Any, station_mapping: Any | None = None, flow_available: bool = True) -> dict[str, Any]:
    validation = validate_observations(data)
    if validation["status"] != "passed": status = "validation_failed"
    elif station_mapping is not None and (pd.DataFrame(station_mapping).get("mapping_status") != "mapped").any(): status = "station_mapping_incomplete"
    elif not flow_available: status = "missing_flow"
    else: status = "real_data_structure_ready"
    return {"status": status, "validation": validation, "validated_real_data": False}
