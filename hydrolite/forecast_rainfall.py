from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hydrolite.forecast_contracts import normalize_rainfall_forecast, validate_rainfall_forecast_frame


def load_forecast_rainfall(path: str | Path) -> pd.DataFrame:
    return normalize_rainfall_forecast(pd.read_csv(Path(path).expanduser().resolve()))


def _member(frame: pd.DataFrame, member_id: str, scenario_type: str, values: np.ndarray | pd.Series) -> pd.DataFrame:
    result = frame.copy()
    result["member_id"] = member_id
    result["scenario_type"] = scenario_type
    result["source"] = "scenario" if scenario_type != "stochastic_demo" else "synthetic"
    result["precipitation_mm"] = np.maximum(np.asarray(values, dtype=float), 0)
    return result


def create_observed_replay_scenario(rainfall: pd.DataFrame) -> pd.DataFrame:
    frame = normalize_rainfall_forecast(rainfall)
    return _member(frame, "baseline", "observed_replay", frame["precipitation_mm"])


def create_design_storm_scenario(total_mm: float, duration_hr: int, pattern: str = "uniform") -> pd.DataFrame:
    if total_mm < 0 or duration_hr <= 0:
        raise ValueError("total_mm must be nonnegative and duration_hr positive")
    weights = np.ones(duration_hr)
    if pattern == "front_loaded":
        weights = np.arange(duration_hr, 0, -1)
    elif pattern == "back_loaded":
        weights = np.arange(1, duration_hr + 1)
    elif pattern == "center_loaded":
        weights = duration_hr - np.abs(np.arange(duration_hr) - (duration_hr - 1) / 2)
    elif pattern == "alternating_block":
        order = np.argsort(np.abs(np.arange(duration_hr) - (duration_hr - 1) / 2))
        weights = np.empty(duration_hr); weights[order] = np.arange(duration_hr, 0, -1)
    elif pattern not in {"uniform", "user_defined"}:
        raise ValueError(f"Unsupported design storm pattern: {pattern}")
    issue = pd.Timestamp("2026-01-01 00:00:00")
    data = pd.DataFrame({"valid_time": pd.date_range(issue, periods=duration_hr, freq="h"), "precipitation_mm": total_mm * weights / weights.sum()})
    data["issue_time"] = issue
    data["scenario_type"] = "design_storm"
    data["source"] = "scenario"
    return normalize_rainfall_forecast(data)


def create_multiplicative_scenarios(rainfall: pd.DataFrame, factors: list[float]) -> pd.DataFrame:
    frame = normalize_rainfall_forecast(rainfall)
    return pd.concat([_member(frame, f"scale_{factor:g}".replace(".", "_"), "uniform_scale", frame["precipitation_mm"] * factor) for factor in factors], ignore_index=True)


def create_temporal_shift_scenarios(rainfall: pd.DataFrame, shifts_hr: list[int]) -> pd.DataFrame:
    frame = normalize_rainfall_forecast(rainfall)
    rows = []
    for shift in shifts_hr:
        values = np.roll(frame["precipitation_mm"].to_numpy(), shift)
        if shift > 0:
            values[:shift] = 0
        elif shift < 0:
            values[shift:] = 0
        name = f"peak_{'late' if shift > 0 else 'early'}_{abs(shift)}h"
        rows.append(_member(frame, name, "temporal_shift", values))
    return pd.concat(rows, ignore_index=True)


def create_peak_intensity_scenarios(rainfall: pd.DataFrame, factors: list[float]) -> pd.DataFrame:
    frame = normalize_rainfall_forecast(rainfall)
    peak = int(frame["precipitation_mm"].idxmax())
    rows = []
    for factor in factors:
        values = frame["precipitation_mm"].to_numpy(copy=True)
        values[peak] *= factor
        rows.append(_member(frame, f"peak_intensity_{factor:g}".replace(".", "_"), "peak_intensity", values))
    return pd.concat(rows, ignore_index=True)


def create_spatial_rainfall_scenarios(rainfall: pd.DataFrame, subbasin_weights: dict[str, float]) -> pd.DataFrame:
    frame = normalize_rainfall_forecast(rainfall)
    return pd.concat([
        _member(frame.assign(subbasin_id=subbasin), f"spatial_{subbasin}", "spatial_distribution", frame["precipitation_mm"] * weight)
        for subbasin, weight in subbasin_weights.items()
    ], ignore_index=True)


def generate_stochastic_rainfall_ensemble(rainfall: pd.DataFrame, members: int, config: dict[str, Any] | None = None, seed: int = 42) -> pd.DataFrame:
    if not 1 <= members <= 20:
        raise ValueError("members must be between 1 and 20")
    frame = normalize_rainfall_forecast(rainfall)
    cfg = config or {}
    maximum = float(cfg.get("max_multiplier", 1.5))
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(members):
        multipliers = np.clip(rng.normal(1.0, float(cfg.get("sigma", 0.15)), len(frame)), 0, maximum)
        rows.append(_member(frame, f"stochastic_{index + 1:02d}", "stochastic_demo", frame["precipitation_mm"] * multipliers))
    return pd.concat(rows, ignore_index=True)


def validate_rainfall_ensemble(ensemble: pd.DataFrame) -> dict[str, Any]:
    result = validate_rainfall_forecast_frame(ensemble)
    member_count = ensemble["member_id"].nunique() if "member_id" in ensemble else 0
    if member_count > 20:
        result["errors"].append("ensemble exceeds 20 members")
        result["status"] = "failed"
    return {**result, "member_count": int(member_count)}


def summarize_rainfall_ensemble(ensemble: pd.DataFrame) -> pd.DataFrame:
    return ensemble.groupby("member_id", as_index=False).agg(
        scenario_type=("scenario_type", "first"),
        total_precipitation_mm=("precipitation_mm", "sum"),
        peak_precipitation_mm=("precipitation_mm", "max"),
        start_time=("valid_time", "min"),
        end_time=("valid_time", "max"),
        points=("valid_time", "size"),
    )


def write_rainfall_ensemble(output_dir: str | Path, result: pd.DataFrame) -> dict[str, Path]:
    root = Path(output_dir).expanduser().resolve()
    charts = root / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    members = root / "rainfall_members.csv"
    summary = root / "rainfall_member_summary.xlsx"
    manifest = root / "rainfall_ensemble_manifest.json"
    result.to_csv(members, index=False)
    summary_frame = summarize_rainfall_ensemble(result)
    summary_frame.to_excel(summary, index=False)
    check = validate_rainfall_ensemble(result)
    manifest.write_text(json.dumps({**check, "ensemble_type": "scenario_ensemble", "seeded": True}, indent=2), encoding="utf-8")
    return {"members": members, "summary": summary, "manifest": manifest, "charts": charts}
