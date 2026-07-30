from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hydrolite.metrics import calculate_all_metrics


def _pairs(observed: Any, simulated: Any) -> pd.DataFrame:
    return pd.DataFrame({
        "observed": pd.to_numeric(pd.Series(observed), errors="coerce"),
        "simulated": pd.to_numeric(pd.Series(simulated), errors="coerce"),
    }).dropna()


def _metric_record(name: str, value: Any, sample_count: int, unit: str = "", window: str = "comparison", warnings: str = "") -> dict[str, Any]:
    return {"metric": name, "value": value, "status": "passed" if pd.notna(value) else "unavailable", "sample_count": sample_count, "unit": unit, "window": window, "warnings": warnings}


def calculate_hindcast_metrics(observed: Any, simulated: Any, timestamps: Any = None, dt_hours: float = 1.0, thresholds: list[float] | None = None) -> dict[str, Any]:
    pairs = _pairs(observed, simulated)
    base = calculate_all_metrics(pairs["observed"], pairs["simulated"])
    n = len(pairs)
    if not n:
        return {"summary": {name: pd.NA for name in ("NSE", "KGE", "PBIAS", "RMSE", "MAE")}, "metrics": pd.DataFrame(), "warnings": ["No aligned pairs."]}
    obs, sim = pairs["observed"], pairs["simulated"]
    times = pd.to_datetime(pd.Series(timestamps), errors="coerce").iloc[pairs.index] if timestamps is not None else pd.Series(pd.RangeIndex(n), index=pairs.index)
    obs_peak, sim_peak = float(obs.max()), float(sim.max())
    obs_idx, sim_idx = obs.idxmax(), sim.idxmax()
    peak_timing = float((pd.Timestamp(times.loc[sim_idx]) - pd.Timestamp(times.loc[obs_idx])).total_seconds() / 3600) if timestamps is not None else float((sim_idx - obs_idx) * dt_hours)
    volume_obs, volume_sim = float(obs.sum() * dt_hours * 3600), float(sim.sum() * dt_hours * 3600)
    log_base = calculate_all_metrics(np.log1p(obs.clip(lower=0)), np.log1p(sim.clip(lower=0)))
    correlation = float(obs.corr(sim)) if obs.std(ddof=0) > 0 and sim.std(ddof=0) > 0 else pd.NA
    centroid_obs = float((np.arange(n) * obs.to_numpy()).sum() / obs.sum()) if obs.sum() else pd.NA
    centroid_sim = float((np.arange(n) * sim.to_numpy()).sum() / sim.sum()) if sim.sum() else pd.NA
    overlap = float(np.minimum(obs.to_numpy(), sim.to_numpy()).sum() / np.maximum(obs.to_numpy(), sim.to_numpy()).sum()) if np.maximum(obs.to_numpy(), sim.to_numpy()).sum() else pd.NA
    rows = [
        *[_metric_record(name, base.get(name), n, "" if name in {"NSE", "KGE", "R2"} else "m3/s" if name in {"RMSE", "MAE"} else "%") for name in ("RMSE", "MAE", "NSE", "KGE", "R2", "PBIAS")],
        _metric_record("log_NSE", log_base.get("NSE"), n),
        _metric_record("volume_error_m3", volume_sim - volume_obs, n, "m3"),
        _metric_record("volume_error_percent", 100 * (volume_sim - volume_obs) / volume_obs if volume_obs else pd.NA, n, "%"),
        _metric_record("peak_flow_error_cms", sim_peak - obs_peak, n, "m3/s"),
        _metric_record("peak_flow_percent_error", 100 * (sim_peak - obs_peak) / obs_peak if obs_peak else pd.NA, n, "%"),
        _metric_record("peak_timing_error_hr", peak_timing, n, "h"),
        _metric_record("time_to_peak_error_hr", peak_timing, n, "h"),
        _metric_record("centroid_timing_error_hr", (centroid_sim - centroid_obs) * dt_hours if pd.notna(centroid_obs) else pd.NA, n, "h"),
        _metric_record("hydrograph_overlap", overlap, n),
        _metric_record("correlation", correlation, n),
    ]
    threshold_rows = []
    for threshold in thresholds or [float(obs.quantile(0.75))]:
        observed_hit = obs >= threshold
        simulated_hit = sim >= threshold
        threshold_rows.append({
            "threshold": threshold, "hit": int((observed_hit & simulated_hit).any()),
            "miss": int((observed_hit & ~simulated_hit).any()), "false_alarm": int((~observed_hit & simulated_hit).any()),
            "duration_error_hr": float((simulated_hit.sum() - observed_hit.sum()) * dt_hours),
        })
    summary = {
        **{name: base.get(name) for name in ("RMSE", "MAE", "NSE", "KGE", "R2", "PBIAS")},
        "log_NSE": log_base.get("NSE"), "volume_error_m3": volume_sim - volume_obs,
        "volume_error_percent": 100 * (volume_sim - volume_obs) / volume_obs if volume_obs else pd.NA,
        "peak_flow_error_cms": sim_peak - obs_peak,
        "peak_flow_percent_error": 100 * (sim_peak - obs_peak) / obs_peak if obs_peak else pd.NA,
        "peak_timing_error_hr": peak_timing, "hydrograph_overlap": overlap,
        "correlation": correlation, "sample_count": n,
    }
    return {"summary": summary, "metrics": pd.DataFrame(rows), "thresholds": pd.DataFrame(threshold_rows), "warnings": base.pop("warnings", [])}


def aggregate_event_metrics(event_metrics: pd.DataFrame) -> pd.DataFrame:
    numeric = [name for name in ("NSE", "KGE", "PBIAS", "RMSE", "MAE", "peak_flow_percent_error", "peak_timing_error_hr", "volume_error_percent") if name in event_metrics]
    rows = []
    for name in numeric:
        values = pd.to_numeric(event_metrics[name], errors="coerce").dropna()
        if values.empty:
            continue
        rows.append({
            "metric": name, "event_count": len(values), "median": float(values.median()),
            "p25": float(values.quantile(0.25)), "p75": float(values.quantile(0.75)),
            "best": float(values.max() if name in {"NSE", "KGE"} else values.abs().min()),
            "worst": float(values.min() if name in {"NSE", "KGE"} else values.iloc[values.abs().argmax()]),
        })
    return pd.DataFrame(rows)


def calculate_metric_median(event_metrics: pd.DataFrame) -> dict[str, float]:
    return {name: float(pd.to_numeric(event_metrics[name], errors="coerce").median()) for name in event_metrics.select_dtypes(include="number")}


def calculate_metric_interquartile_range(event_metrics: pd.DataFrame) -> dict[str, float]:
    return {name: float(pd.to_numeric(event_metrics[name], errors="coerce").quantile(.75) - pd.to_numeric(event_metrics[name], errors="coerce").quantile(.25)) for name in event_metrics.select_dtypes(include="number")}


def calculate_metric_worst_case(event_metrics: pd.DataFrame) -> dict[str, Any]:
    if event_metrics.empty or "NSE" not in event_metrics:
        return {}
    idx = pd.to_numeric(event_metrics["NSE"], errors="coerce").idxmin()
    return event_metrics.loc[idx].to_dict()


def calculate_event_success_rate(event_metrics: pd.DataFrame) -> float:
    return float(event_metrics.get("run_status", pd.Series(dtype=str)).eq("success").mean()) if len(event_metrics) else 0.0


def summarize_metrics_by_event_magnitude(events: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    merged = metrics.merge(events[["event_id", "peak_flow_cms"]], on="event_id", how="left", suffixes=("", "_observed"))
    merged["magnitude_class"] = pd.qcut(pd.to_numeric(merged["peak_flow_cms"], errors="coerce"), q=min(3, len(merged)), labels=["small", "medium", "large"][-min(3, len(merged)):], duplicates="drop") if len(merged) > 1 else "single"
    return merged.groupby("magnitude_class", observed=True).agg(event_count=("event_id", "count"), median_NSE=("NSE", "median"), median_KGE=("KGE", "median")).reset_index()


def summarize_metrics_by_season(events: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    merged = metrics.merge(events[["event_id", "rainfall_start"]], on="event_id", how="left")
    month = pd.to_datetime(merged["rainfall_start"], errors="coerce").dt.month
    merged["season"] = month.map({12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"})
    return merged.groupby("season", dropna=False).agg(event_count=("event_id", "count"), median_NSE=("NSE", "median"), median_KGE=("KGE", "median")).reset_index()


def summarize_metrics_by_initial_condition(events: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    merged = metrics.merge(events[["event_id", "initial_flow_cms"]], on="event_id", how="left")
    merged["initial_condition"] = pd.cut(pd.to_numeric(merged["initial_flow_cms"], errors="coerce"), bins=[-np.inf, .5, 2, np.inf], labels=["low", "medium", "high"])
    return merged.groupby("initial_condition", observed=True).agg(event_count=("event_id", "count"), median_NSE=("NSE", "median")).reset_index()


def classify_hindcast_performance(summary: pd.DataFrame, config: dict[str, Any] | None = None) -> str:
    nse = summary.loc[summary["metric"] == "NSE", "median"]
    if nse.empty:
        return "insufficient_events"
    value = float(nse.iloc[0])
    if value >= .75:
        return "strong_consistency"
    if value >= .5:
        return "moderate_consistency"
    if value >= 0:
        return "variable_performance"
    return "weak_consistency"
