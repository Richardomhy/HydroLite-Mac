from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _flow_frame(series: Any) -> pd.DataFrame:
    if isinstance(series, pd.DataFrame):
        timestamp_column = next((name for name in ("timestamp", "datetime", "time") if name in series.columns), None)
        flow_column = next((name for name in ("flow_cms", "flow", "value") if name in series.columns), None)
        if timestamp_column is None or flow_column is None:
            raise ValueError("Flow data requires timestamp and flow_cms columns.")
        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(series[timestamp_column], errors="coerce"),
                "flow_cms": pd.to_numeric(series[flow_column], errors="coerce"),
            }
        )
    elif isinstance(series, pd.Series):
        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(series.index, errors="coerce"),
                "flow_cms": pd.to_numeric(series, errors="coerce"),
            }
        )
    else:
        raise TypeError("Flow series must be a pandas DataFrame or Series.")
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def calculate_peak_flow(series: Any) -> dict[str, Any]:
    frame = _flow_frame(series)
    valid = frame.dropna(subset=["flow_cms"])
    if valid.empty:
        return {"peak_flow_cms": None, "peak_time": None}
    index = valid["flow_cms"].idxmax()
    return {
        "peak_flow_cms": float(valid.loc[index, "flow_cms"]),
        "peak_time": pd.Timestamp(valid.loc[index, "timestamp"]).isoformat(),
    }


def calculate_time_to_peak(series: Any, event_start: str | pd.Timestamp | None = None) -> float | None:
    frame = _flow_frame(series)
    peak = calculate_peak_flow(frame)
    if peak["peak_time"] is None or frame.empty:
        return None
    start = pd.Timestamp(event_start) if event_start is not None else pd.Timestamp(frame["timestamp"].iloc[0])
    return float((pd.Timestamp(peak["peak_time"]) - start).total_seconds() / 3600.0)


def calculate_runoff_volume(series: Any) -> float | None:
    frame = _flow_frame(series).dropna(subset=["flow_cms"])
    if len(frame) < 2:
        return None
    elapsed = (frame["timestamp"] - frame["timestamp"].iloc[0]).dt.total_seconds().to_numpy(dtype=float)
    values = frame["flow_cms"].to_numpy(dtype=float)
    return float(np.trapezoid(values, elapsed))


def calculate_hydrograph_centroid_time(series: Any) -> str | None:
    frame = _flow_frame(series).dropna(subset=["flow_cms"])
    if len(frame) < 2:
        return None
    elapsed = (frame["timestamp"] - frame["timestamp"].iloc[0]).dt.total_seconds().to_numpy(dtype=float)
    values = frame["flow_cms"].clip(lower=0).to_numpy(dtype=float)
    volume = float(np.trapezoid(values, elapsed))
    if volume <= 0:
        return None
    first_moment = float(np.trapezoid(values * elapsed, elapsed))
    centroid = pd.Timestamp(frame["timestamp"].iloc[0]) + pd.to_timedelta(first_moment / volume, unit="s")
    return centroid.isoformat()


def calculate_rising_limb_duration(series: Any) -> float | None:
    frame = _flow_frame(series)
    peak = calculate_peak_flow(frame)
    if frame.empty or peak["peak_time"] is None:
        return None
    return float((pd.Timestamp(peak["peak_time"]) - frame["timestamp"].iloc[0]).total_seconds() / 3600.0)


def calculate_recession_limb_duration(series: Any) -> float | None:
    frame = _flow_frame(series)
    peak = calculate_peak_flow(frame)
    if frame.empty or peak["peak_time"] is None:
        return None
    return float((frame["timestamp"].iloc[-1] - pd.Timestamp(peak["peak_time"])).total_seconds() / 3600.0)


def calculate_duration_above_threshold(series: Any, threshold: float) -> float | None:
    frame = _flow_frame(series).dropna(subset=["flow_cms"])
    if len(frame) < 2:
        return None
    duration = 0.0
    for left, right in zip(frame.iloc[:-1].itertuples(), frame.iloc[1:].itertuples()):
        left_flow = float(left.flow_cms)
        right_flow = float(right.flow_cms)
        seconds = (right.timestamp - left.timestamp).total_seconds()
        if left_flow > threshold and right_flow > threshold:
            duration += seconds
        elif (left_flow > threshold) != (right_flow > threshold) and right_flow != left_flow:
            crossing_fraction = (float(threshold) - left_flow) / (right_flow - left_flow)
            duration += seconds * ((1.0 - crossing_fraction) if right_flow > threshold else crossing_fraction)
    return float(duration / 3600.0)


def calculate_event_flow_metrics(series: Any, thresholds: list[float] | None = None) -> dict[str, Any]:
    frame = _flow_frame(series)
    valid = frame.dropna(subset=["flow_cms"])
    peak = calculate_peak_flow(frame)
    volume = calculate_runoff_volume(frame)
    event_start = frame["timestamp"].iloc[0].isoformat() if not frame.empty else None
    event_end = frame["timestamp"].iloc[-1].isoformat() if not frame.empty else None
    duration = (
        float((frame["timestamp"].iloc[-1] - frame["timestamp"].iloc[0]).total_seconds() / 3600.0)
        if len(frame) >= 2
        else None
    )
    user_thresholds = thresholds is not None
    if thresholds is None and peak["peak_flow_cms"] is not None:
        thresholds = [peak["peak_flow_cms"] * fraction for fraction in (0.5, 0.75, 0.9)]
    threshold_metrics = [
        {
            "threshold_cms": float(threshold),
            "threshold_type": "user_absolute_threshold" if user_thresholds else "diagnostic_relative_threshold",
            "duration_above_hr": calculate_duration_above_threshold(frame, float(threshold)),
        }
        for threshold in (thresholds or [])
    ]
    return {
        **peak,
        "time_to_peak_hr": calculate_time_to_peak(frame),
        "runoff_volume_m3": volume,
        "centroid_time": calculate_hydrograph_centroid_time(frame),
        "rising_limb_duration_hr": calculate_rising_limb_duration(frame),
        "recession_limb_duration_hr": calculate_recession_limb_duration(frame),
        "event_start": event_start,
        "event_end": event_end,
        "duration_hr": duration,
        "base_flow_start": None,
        "peak_to_volume_ratio": (
            float(peak["peak_flow_cms"] / volume)
            if peak["peak_flow_cms"] is not None and volume not in (None, 0)
            else None
        ),
        "records": int(len(frame)),
        "missing_count": int(frame["flow_cms"].isna().sum()),
        "thresholds": threshold_metrics,
        "threshold_note": "Relative thresholds are event diagnostics, not statutory flood-warning levels.",
    }


def compare_event_flow_metrics(hms_metrics: dict[str, Any], hydrolite_metrics: dict[str, Any]) -> dict[str, Any]:
    def difference(name: str) -> float | None:
        left, right = hms_metrics.get(name), hydrolite_metrics.get(name)
        return float(right - left) if left is not None and right is not None else None

    def percent(name: str) -> float | None:
        left, right = hms_metrics.get(name), hydrolite_metrics.get(name)
        return float((right - left) / left * 100.0) if left not in (None, 0) and right is not None else None

    hms_peak_time = hms_metrics.get("peak_time")
    hydrolite_peak_time = hydrolite_metrics.get("peak_time")
    peak_timing_difference = (
        float((pd.Timestamp(hydrolite_peak_time) - pd.Timestamp(hms_peak_time)).total_seconds() / 3600.0)
        if hms_peak_time and hydrolite_peak_time
        else None
    )
    hms_centroid = hms_metrics.get("centroid_time")
    hydrolite_centroid = hydrolite_metrics.get("centroid_time")
    centroid_difference = (
        float((pd.Timestamp(hydrolite_centroid) - pd.Timestamp(hms_centroid)).total_seconds() / 3600.0)
        if hms_centroid and hydrolite_centroid
        else None
    )
    return {
        "peak_flow_difference_cms": difference("peak_flow_cms"),
        "peak_flow_percent_difference": percent("peak_flow_cms"),
        "peak_timing_difference_hr": peak_timing_difference,
        "runoff_volume_difference_m3": difference("runoff_volume_m3"),
        "runoff_volume_percent_difference": percent("runoff_volume_m3"),
        "centroid_timing_difference_hr": centroid_difference,
    }


def validate_event_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    required = {"peak_flow_cms", "peak_time", "runoff_volume_m3", "records", "missing_count"}
    missing = sorted(required - set(metrics))
    errors = [f"Missing metric: {name}" for name in missing]
    if metrics.get("records", 0) < 2:
        errors.append("At least two records are required for event-volume metrics.")
    if metrics.get("peak_flow_cms") is not None and metrics["peak_flow_cms"] < 0:
        errors.append("Peak flow must not be negative.")
    return {"status": "passed" if not errors else "failed", "errors": errors}
