"""Strict concentration-to-load ledger with explicit alignment provenance."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hydrolite.water_quality_contracts import ALIGNMENT_METHODS


KG_DAY_FACTOR = 86.4  # mg/L * m3/s * 86.4 = kg/day


def concentration_flow_to_load(concentration_mg_l: Any, flow_cms: Any) -> np.ndarray:
    concentration = np.asarray(concentration_mg_l, dtype=float)
    flow = np.asarray(flow_cms, dtype=float)
    result = concentration * flow * KG_DAY_FACTOR
    result[(concentration < 0) | (flow < 0) | ~np.isfinite(concentration) | ~np.isfinite(flow)] = np.nan
    return result


def align_concentration_and_flow(observations: Any, flow: Any, method: str = "daily", tolerance: str = "12h") -> pd.DataFrame:
    if method not in ALIGNMENT_METHODS:
        raise ValueError(f"Unsupported alignment method: {method}")
    obs = pd.DataFrame(observations).copy(); hydro = pd.DataFrame(flow).copy()
    obs["timestamp"] = pd.to_datetime(obs["timestamp"]); hydro["timestamp"] = pd.to_datetime(hydro["timestamp"])
    flow_column = "flow_cms" if "flow_cms" in hydro else "flow"
    if method in {"daily", "daily_aggregation"}:
        obs["alignment_time"] = obs.timestamp.dt.floor("D"); hydro["alignment_time"] = hydro.timestamp.dt.floor("D")
        merged = obs.merge(hydro[["alignment_time", "station_id", flow_column, *(["source"] if "source" in hydro else [])]], on=["alignment_time", "station_id"], how="left", suffixes=("", "_flow"))
    elif method == "exact":
        merged = obs.merge(hydro[["timestamp", "station_id", flow_column, *(["source"] if "source" in hydro else [])]], on=["timestamp", "station_id"], how="left", suffixes=("", "_flow"))
    else:
        parts = []
        for station, group in obs.groupby("station_id", sort=False):
            right = hydro[hydro.station_id.astype(str) == str(station)].sort_values("timestamp")
            parts.append(pd.merge_asof(group.sort_values("timestamp"), right[["timestamp", flow_column, *(["source"] if "source" in right else [])]], on="timestamp", direction="nearest", tolerance=pd.Timedelta(tolerance), suffixes=("", "_flow")))
        merged = pd.concat(parts, ignore_index=True)
    merged = merged.rename(columns={flow_column: "flow_cms"})
    merged["load_kg_day"] = concentration_flow_to_load(merged["value"], merged["flow_cms"])
    merged["load_status"] = np.where(merged.flow_cms.isna(), "flow_unavailable", np.where(merged.load_kg_day.isna(), "unavailable", "available"))
    merged["alignment_method"] = method
    merged["alignment_tolerance"] = tolerance if method == "nearest_with_tolerance" else "not_applicable"
    merged["source_concentration"] = merged.get("source", "user")
    merged["source_flow"] = merged.get("source_flow", merged.get("source_y", "user"))
    merged["concentration_source"] = merged["source_concentration"]
    merged["flow_source"] = merged["source_flow"]
    merged["timestamp_alignment"] = method
    merged["interpolation_method"] = "none" if method in {"exact", "daily", "daily_aggregation"} else "nearest_with_tolerance"
    merged["unit_conversion"] = "mg/L * m3/s * 86.4 = kg/day"
    merged["result_quality"] = merged["load_status"]
    return merged


def summarize_loads(ledger: Any) -> pd.DataFrame:
    frame = pd.DataFrame(ledger)
    return frame.groupby(["station_id", "variable_id"], as_index=False).agg(
        available_days=("load_status", lambda value: int((value == "available").sum())),
        unavailable_days=("load_status", lambda value: int((value != "available").sum())),
        mean_load_kg_day=("load_kg_day", "mean"), max_load_kg_day=("load_kg_day", "max"), total_load_kg=("load_kg_day", "sum"),
    )


def calculate_load_from_concentration_flow(concentration_mg_l: Any, flow_cms: Any) -> np.ndarray:
    return concentration_flow_to_load(concentration_mg_l, flow_cms)


calculate_instantaneous_load = calculate_load_from_concentration_flow
calculate_daily_load = calculate_load_from_concentration_flow
calculate_interval_load = calculate_load_from_concentration_flow
align_water_quality_and_flow = align_concentration_and_flow
aggregate_load = summarize_loads


def validate_load_units(concentration_unit: str, flow_unit: str, load_unit: str = "kg/day") -> dict[str, Any]:
    expected = ("mg/L", "m3/s", "kg/day")
    supplied = (concentration_unit, flow_unit, load_unit)
    return {"status": "passed" if supplied == expected else "failed", "supplied": supplied, "expected": expected, "conversion_factor": KG_DAY_FACTOR}


def write_load_ledger(ledger: Any, output_dir: str | Any) -> dict[str, Any]:
    from pathlib import Path
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); csv = root / "concentration_load_ledger.csv"; xlsx = root / "load_summary.xlsx"; pd.DataFrame(ledger).to_csv(csv, index=False); summarize_loads(ledger).to_excel(xlsx, index=False); return {"ledger": csv, "summary": xlsx}
