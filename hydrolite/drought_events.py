from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def detect_drought_events(index_series: pd.Series, threshold: float = -1.0, min_duration: int = 2) -> list[dict[str, Any]]:
    if min_duration < 2:
        raise ValueError("min_duration must be at least 2; a single low day/month is not a long drought event")
    series = pd.to_numeric(index_series, errors="coerce")
    dates = pd.to_datetime(series.index)
    events, start = [], None
    for position, (date, value) in enumerate(zip(dates, series)):
        active = pd.notna(value) and float(value) <= threshold
        if active and start is None:
            start = position
        if start is not None and (not active or position == len(series) - 1):
            end = position if active and position == len(series) - 1 else position - 1
            if end - start + 1 >= min_duration:
                part = series.iloc[start : end + 1]
                events.append({
                    "start": dates[start],
                    "end": dates[end],
                    "values": part,
                    "data_quality": "ready" if part.notna().all() else "limited",
                    "warnings": [],
                })
            start = None
    return events


def merge_drought_periods(events: list[dict[str, Any]], gap_tolerance: int = 1) -> list[dict[str, Any]]:
    if not events:
        return []
    merged = [dict(events[0])]
    for event in events[1:]:
        previous = merged[-1]
        gap = (pd.Timestamp(event["start"]).to_period("M") - pd.Timestamp(previous["end"]).to_period("M")).n - 1
        if gap <= gap_tolerance:
            previous["end"] = event["end"]
            previous["values"] = pd.concat([previous["values"], event["values"]]).sort_index()
            previous["warnings"] = sorted(set(previous.get("warnings", []) + [f"merged_across_{max(gap, 0)}_period_gap"]))
        else:
            merged.append(dict(event))
    return merged


def calculate_drought_event_metrics(event: dict[str, Any]) -> dict[str, Any]:
    values = pd.to_numeric(event["values"], errors="coerce").dropna()
    deficits = (-values).clip(lower=0)
    start, end = pd.Timestamp(event["start"]), pd.Timestamp(event["end"])
    return {
        "start": start,
        "end": end,
        "duration": int(len(values)),
        "minimum_index": float(values.min()) if len(values) else np.nan,
        "mean_index": float(values.mean()) if len(values) else np.nan,
        "cumulative_deficit": float(deficits.sum()),
        "maximum_deficit": float(deficits.max()) if len(deficits) else np.nan,
        "recovery_duration": event.get("recovery_duration"),
        "affected_subbasins": event.get("affected_subbasins", "all"),
        "affected_area": event.get("affected_area"),
        "dominant_drought_type": event.get("dominant_drought_type", "unresolved"),
        "data_quality": event.get("data_quality", "unknown"),
        "warnings": "; ".join(event.get("warnings", [])),
    }


def classify_drought_event(event: dict[str, Any]) -> str:
    minimum = float(calculate_drought_event_metrics(event)["minimum_index"])
    if minimum <= -2: return "extreme"
    if minimum <= -1.5: return "severe"
    if minimum <= -1: return "moderate"
    return "mild"


def build_drought_event_catalog(results: dict[str, pd.Series] | pd.DataFrame, threshold: float = -1.0, min_duration: int = 2) -> pd.DataFrame:
    frame = pd.DataFrame(results)
    rows = []
    sequence = 1
    for column in frame.select_dtypes(include="number"):
        for event in merge_drought_periods(detect_drought_events(frame[column].dropna(), threshold, min_duration)):
            metrics = calculate_drought_event_metrics({**event, "dominant_drought_type": column})
            rows.append({"event_id": f"DROUGHT-{sequence:03d}", "classification": classify_drought_event(event), **metrics})
            sequence += 1
    columns = ["event_id", "start", "end", "duration", "minimum_index", "mean_index", "cumulative_deficit", "maximum_deficit", "recovery_duration", "affected_subbasins", "affected_area", "dominant_drought_type", "data_quality", "warnings", "classification"]
    return pd.DataFrame(rows, columns=columns)


def compare_drought_events_across_indices(catalogs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat([frame.assign(index_name=name) for name, frame in catalogs.items() if not frame.empty], ignore_index=True) if any(not frame.empty for frame in catalogs.values()) else pd.DataFrame()


def write_drought_event_report(output_dir: str | Path, result: pd.DataFrame) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx = output / "drought_event_catalog.xlsx"
    result.to_excel(xlsx, index=False)
    report = output / "drought_event_report.md"
    report.write_text(
        "# Historical drought event catalog\n\n"
        f"- event_count: `{len(result)}`\n\n"
        "Events require at least two consecutive periods below the configured diagnostic threshold. They are not statutory drought declarations.\n",
        encoding="utf-8",
    )
    if not result.empty:
        fig, ax = plt.subplots(figsize=(10, 3.5))
        for index, row in result.iterrows():
            ax.plot([pd.Timestamp(row.start), pd.Timestamp(row.end)], [index, index], linewidth=6)
        ax.set_ylabel("event"); fig.tight_layout(); fig.savefig(output / "drought_event_timeline.png", dpi=130); plt.close(fig)
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.scatter(result["duration"], result["cumulative_deficit"]); ax.set_xlabel("duration"); ax.set_ylabel("severity")
        fig.tight_layout(); fig.savefig(output / "drought_severity_duration.png", dpi=130); plt.close(fig)
    return {"catalog": xlsx, "report": report}
