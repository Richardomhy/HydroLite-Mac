from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
import json

import pandas as pd


DEFAULT_CONFIG = {
    "method": "combined_rainfall_flow",
    "rainfall_threshold_mm": 0.1,
    "inter_event_time_hr": 12,
    "flow_rise_fraction": 0.15,
    "antecedent_window_hr": 24,
    "recession_window_hr": 12,
}


def _frame(data: Any, key: str = "rainfall") -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, dict):
        value = data.get(key, data.get("data"))
        return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
    path = Path(data)
    if path.is_dir():
        for name in (f"{key}.csv", "rainfall.csv"):
            if (path / name).exists():
                return pd.read_csv(path / name)
    return pd.read_csv(path)


def _time_column(frame: pd.DataFrame) -> str:
    for name in ("timestamp", "datetime", "time"):
        if name in frame:
            return name
    raise ValueError("Time series requires timestamp, datetime, or time.")


def assign_event_id(event: dict[str, Any]) -> str:
    start = pd.Timestamp(event["rainfall_start"])
    suffix = str(event.get("station_id", "ALL")).replace(" ", "_")
    return f"FE_{start:%Y%m%d_%H%M}_{suffix}"


def merge_event_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: pd.Timestamp(item["rainfall_start"]))
    merged = [dict(ordered[0])]
    for item in ordered[1:]:
        previous = merged[-1]
        if pd.Timestamp(item["rainfall_start"]) <= pd.Timestamp(previous["analysis_end"]):
            previous["rainfall_end"] = max(pd.Timestamp(previous["rainfall_end"]), pd.Timestamp(item["rainfall_end"]))
            previous["analysis_end"] = max(pd.Timestamp(previous["analysis_end"]), pd.Timestamp(item["analysis_end"]))
            previous.setdefault("warnings", []).append("Overlapping candidate merged.")
        else:
            merged.append(dict(item))
    return merged


def split_overlapping_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted((dict(item) for item in events), key=lambda item: pd.Timestamp(item["rainfall_start"]))
    for left, right in zip(ordered, ordered[1:]):
        if pd.Timestamp(left["analysis_end"]) >= pd.Timestamp(right["warmup_start"]):
            boundary = pd.Timestamp(right["rainfall_start"]) - pd.Timedelta(seconds=1)
            left["analysis_end"] = min(pd.Timestamp(left["analysis_end"]), boundary)
            left.setdefault("warnings", []).append("Analysis window clipped to avoid event overlap.")
    return ordered


def calculate_antecedent_window(event: dict[str, Any], data: Any = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(event["rainfall_start"])
    hours = float(event.get("antecedent_window_hr", DEFAULT_CONFIG["antecedent_window_hr"]))
    return start - pd.Timedelta(hours=hours), start


def calculate_event_recession_window(event: dict[str, Any], data: Any = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp(event.get("runoff_end", event["rainfall_end"]))
    hours = float(event.get("recession_window_hr", DEFAULT_CONFIG["recession_window_hr"]))
    return end, end + pd.Timedelta(hours=hours)


def _event_from_group(event_id: str, rain: pd.DataFrame, flow: pd.DataFrame | None, config: dict[str, Any]) -> dict[str, Any]:
    time_col = _time_column(rain)
    rain = rain.copy()
    rain[time_col] = pd.to_datetime(rain[time_col], errors="coerce")
    rain_col = next((name for name in ("rainfall_mm", "rain_mm", "precipitation_mm") if name in rain), None)
    if rain_col is None:
        raise ValueError("Rainfall data requires rainfall_mm, rain_mm, or precipitation_mm.")
    active = rain[pd.to_numeric(rain[rain_col], errors="coerce").fillna(0) > float(config["rainfall_threshold_mm"])]
    start = active[time_col].min() if not active.empty else rain[time_col].min()
    rain_end = active[time_col].max() if not active.empty else rain[time_col].max()
    peak_time, peak_flow, initial_flow, runoff_end = rain_end, None, None, rain[time_col].max()
    runoff_volume = None
    if flow is not None and not flow.empty:
        flow = flow.copy()
        ft = _time_column(flow)
        flow[ft] = pd.to_datetime(flow[ft], errors="coerce")
        fc = next((name for name in ("flow_cms", "observed_streamflow_m3s", "outflow_cms") if name in flow), None)
        if fc:
            values = pd.to_numeric(flow[fc], errors="coerce")
            if values.notna().any():
                idx = values.idxmax()
                peak_time, peak_flow = flow.loc[idx, ft], float(values.loc[idx])
                initial_flow = float(values.dropna().iloc[0])
                runoff_end = flow[ft].max()
                interval = flow[ft].sort_values().diff().dt.total_seconds().median()
                runoff_volume = float(values.fillna(0).sum() * (interval if pd.notna(interval) else 3600))
    warmup = pd.Timestamp(start) - pd.Timedelta(hours=float(config["antecedent_window_hr"]))
    analysis_end = pd.Timestamp(runoff_end) + pd.Timedelta(hours=float(config["recession_window_hr"]))
    event = {
        "event_id": event_id,
        "event_name": event_id,
        "rainfall_start": start,
        "rainfall_end": rain_end,
        "runoff_start": start,
        "peak_time": peak_time,
        "runoff_end": runoff_end,
        "warmup_start": warmup,
        "analysis_end": analysis_end,
        "duration_hr": (analysis_end - warmup).total_seconds() / 3600,
        "antecedent_window_hr": float(config["antecedent_window_hr"]),
        "total_rainfall_mm": float(pd.to_numeric(rain[rain_col], errors="coerce").sum()),
        "maximum_intensity_mm_hr": float(pd.to_numeric(rain[rain_col], errors="coerce").max()),
        "peak_flow_cms": peak_flow,
        "runoff_volume_m3": runoff_volume,
        "initial_flow_cms": initial_flow,
        "initial_stage_m": None,
        "stations": ",".join(sorted(set(rain.get("station_id", pd.Series(["ALL"])).dropna().astype(str)))),
        "spatial_coverage": 1.0,
        "temporal_coverage": float(rain[rain_col].notna().mean()),
        "quality_status": "accepted",
        "observed_is_synthetic": bool(rain.get("synthetic_demo", pd.Series([False])).astype(str).str.lower().isin(["true", "1"]).any()),
        "included_for_calibration": False,
        "included_for_validation": False,
        "included_for_test": False,
        "exclusion_reason": "",
        "warnings": [],
    }
    return event


def detect_flood_events(rainfall: Any, flow: Any = None, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    rain = _frame(rainfall)
    flow_frame = _frame(flow, "streamflow") if flow is not None else None
    if "event_id" in rain:
        events = []
        for event_id, group in rain.groupby("event_id", sort=True):
            matching = None
            if flow_frame is not None:
                matching = flow_frame[flow_frame["event_id"].astype(str) == str(event_id)] if "event_id" in flow_frame else flow_frame
            events.append(_event_from_group(str(event_id), group, matching, cfg))
        return events

    time_col = _time_column(rain)
    rain_col = next((name for name in ("rainfall_mm", "rain_mm", "precipitation_mm") if name in rain), None)
    if rain_col is None:
        raise ValueError("Rainfall data requires rainfall_mm, rain_mm, or precipitation_mm.")
    work = rain.copy()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    work = work.sort_values(time_col)
    active = work[pd.to_numeric(work[rain_col], errors="coerce").fillna(0) > float(cfg["rainfall_threshold_mm"])]
    if active.empty:
        return []
    gaps = active[time_col].diff().dt.total_seconds().div(3600).fillna(float("inf"))
    groups = (gaps > float(cfg["inter_event_time_hr"])).cumsum()
    events = []
    for _, group in active.groupby(groups):
        start, end = group[time_col].min(), group[time_col].max()
        window = work[(work[time_col] >= start) & (work[time_col] <= end)]
        event = _event_from_group("", window, flow_frame, cfg)
        event["event_id"] = assign_event_id(event)
        event["event_name"] = event["event_id"]
        events.append(event)
    return split_overlapping_events(events)


def validate_flood_event(event: dict[str, Any]) -> dict[str, Any]:
    errors = []
    required = ("event_id", "rainfall_start", "rainfall_end", "warmup_start", "analysis_end")
    errors.extend(f"missing {name}" for name in required if event.get(name) in (None, ""))
    if not errors:
        ordered = [pd.Timestamp(event[name]) for name in ("warmup_start", "rainfall_start", "rainfall_end", "analysis_end")]
        if ordered != sorted(ordered):
            errors.append("event times must satisfy warmup_start <= rainfall_start <= rainfall_end <= analysis_end")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def classify_event_quality(event: dict[str, Any]) -> str:
    if validate_flood_event(event)["status"] == "failed":
        return "rejected"
    coverage = float(event.get("temporal_coverage") or 0)
    if coverage < 0.8:
        return "insufficient_coverage"
    if event.get("warnings"):
        return "accepted_with_warnings"
    return "accepted"


def build_event_catalog(data: Any, config: dict[str, Any] | None = None) -> pd.DataFrame:
    if isinstance(data, dict):
        events = detect_flood_events(data.get("rainfall", data), data.get("flow"), config)
    else:
        root = Path(data)
        rain = root / "rainfall.csv" if root.is_dir() else root
        flow = root / "streamflow.csv" if root.is_dir() and (root / "streamflow.csv").exists() else None
        events = detect_flood_events(rain, flow, config)
    for event in events:
        event["quality_status"] = classify_event_quality(event)
        event["warnings"] = "; ".join(event.get("warnings", []))
    return pd.DataFrame(events)


def write_event_catalog(output_dir: str | Path, result: pd.DataFrame | list[dict[str, Any]]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = result if isinstance(result, pd.DataFrame) else pd.DataFrame(result)
    csv_path = output / "flood_event_catalog.csv"
    xlsx_path = output / "flood_event_catalog.xlsx"
    frame.to_csv(csv_path, index=False)
    frame.to_excel(xlsx_path, index=False)
    summary = {
        "event_count": int(len(frame)),
        "accepted_count": int(frame.get("quality_status", pd.Series(dtype=str)).isin(["accepted", "accepted_with_warnings"]).sum()),
        "synthetic_event_count": int(frame.get("observed_is_synthetic", pd.Series(dtype=bool)).astype(bool).sum()),
    }
    for language, title in (("zh", "洪水事件识别报告"), ("en", "Flood Event Detection Report")):
        path = output / f"event_detection_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Event count: `{summary['event_count']}`\n"
            f"- Accepted: `{summary['accepted_count']}`\n"
            f"- Synthetic demo events: `{summary['synthetic_event_count']}`\n"
            "- Automatic boundaries require user confirmation before real calibration or validation.\n",
            encoding="utf-8",
        )
    (output / "event_catalog_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"csv": csv_path, "xlsx": xlsx_path}
