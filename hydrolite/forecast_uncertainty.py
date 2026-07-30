from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]


def collect_forecast_members(results: list[pd.DataFrame] | pd.DataFrame) -> pd.DataFrame:
    return results.copy() if isinstance(results, pd.DataFrame) else pd.concat(results, ignore_index=True)


def validate_forecast_members(results: pd.DataFrame) -> dict[str, Any]:
    required = {"member_id", "valid_time", "outlet_flow_cms", "run_status"}
    missing = sorted(required - set(results.columns))
    bad = int((pd.to_numeric(results.get("outlet_flow_cms", pd.Series(dtype=float)), errors="coerce") < 0).sum())
    return {"status": "passed" if not missing and bad == 0 else "failed", "missing": missing, "negative_flow_count": bad}


def calculate_ensemble_quantiles(results: pd.DataFrame, quantiles: list[float] | None = None) -> pd.DataFrame:
    q = quantiles or DEFAULT_QUANTILES
    success = results[results["run_status"] == "success"].copy()
    rows = []
    for valid_time, group in success.groupby("valid_time"):
        values = group["outlet_flow_cms"].to_numpy(float)
        row = {"valid_time": valid_time, "member_count": len(values)}
        row.update({f"p{int(value * 100):02d}": float(np.quantile(values, value)) for value in q})
        rows.append(row)
    return pd.DataFrame(rows)


def calculate_exceedance_probability(results: pd.DataFrame, thresholds: list[dict[str, Any]] | dict[str, float]) -> pd.DataFrame:
    specs = thresholds if isinstance(thresholds, list) else [{"name": key, "threshold": value, "source": "user_config"} for key, value in thresholds.items()]
    peaks = results.groupby("member_id")["outlet_flow_cms"].max()
    return pd.DataFrame([
        {
            "threshold_name": spec.get("name", "threshold"),
            "threshold": float(spec["threshold"]),
            "scenario_member_exceedance_fraction": float((peaks >= float(spec["threshold"])).mean()),
            "members_exceeding": int((peaks >= float(spec["threshold"])).sum()),
            "threshold_source": spec.get("source", "user_config"),
        }
        for spec in specs
    ])


def _distribution(results: pd.DataFrame, column: str, aggregate: str) -> pd.DataFrame:
    grouped = results.groupby("member_id")[column]
    values = grouped.max() if aggregate == "max" else grouped.sum()
    return pd.DataFrame([{"metric": column, **{f"p{int(q * 100):02d}": float(values.quantile(q)) for q in DEFAULT_QUANTILES}}])


def calculate_peak_distribution(results: pd.DataFrame) -> pd.DataFrame:
    return _distribution(results, "outlet_flow_cms", "max")


def calculate_peak_time_distribution(results: pd.DataFrame) -> pd.DataFrame:
    success = results[results["run_status"] == "success"].copy()
    peak_rows = success.loc[success.groupby("member_id")["outlet_flow_cms"].idxmax()]
    issue = pd.to_datetime(peak_rows["issue_time"])
    hours = (pd.to_datetime(peak_rows["valid_time"]) - issue).dt.total_seconds() / 3600
    return pd.DataFrame([{"metric": "peak_time_lead_hr", **{f"p{int(q * 100):02d}": float(hours.quantile(q)) for q in DEFAULT_QUANTILES}}])


def calculate_volume_distribution(results: pd.DataFrame) -> pd.DataFrame:
    interval = results["interval_minutes"].astype(float) * 60
    frame = results.assign(volume_m3=results["outlet_flow_cms"].astype(float) * interval)
    return _distribution(frame, "volume_m3", "sum")


def calculate_reservoir_stage_distribution(results: pd.DataFrame) -> pd.DataFrame:
    if "reservoir_stage_m" not in results or results["reservoir_stage_m"].dropna().empty:
        return pd.DataFrame([{"metric": "reservoir_stage_m", **{f"p{int(q*100):02d}": np.nan for q in DEFAULT_QUANTILES}}])
    rows = [_distribution(results.dropna(subset=["reservoir_stage_m"]), "reservoir_stage_m", "max")]
    if "reservoir_storage_m3" in results and not results["reservoir_storage_m3"].dropna().empty:
        rows.append(_distribution(results.dropna(subset=["reservoir_storage_m3"]), "reservoir_storage_m3", "max"))
    return pd.concat(rows, ignore_index=True)


def calculate_prediction_interval_coverage(observed, intervals: pd.DataFrame) -> float:
    values = np.asarray(observed, float)
    return float(np.mean((values >= intervals["p05"]) & (values <= intervals["p95"])))


def calculate_interval_sharpness(intervals: pd.DataFrame) -> float:
    return float((intervals["p95"] - intervals["p05"]).mean())


def classify_uncertainty_sources(config: dict[str, Any] | None = None) -> pd.DataFrame:
    active = set((config or {}).get("sources", ["rainfall_input", "model_structure", "reservoir_curve", "initial_condition", "unresolved"]))
    all_sources = ["rainfall_input", "hydrologic_parameter", "model_structure", "reservoir_curve", "initial_condition", "data_driven_residual", "unresolved"]
    return pd.DataFrame({"uncertainty_source": all_sources, "status": ["active" if item in active else "not_evaluated" for item in all_sources]})


def load_user_flood_thresholds(path: str | Path) -> list[dict[str, Any]]:
    import yaml
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return payload.get("thresholds", [])


def validate_flood_thresholds(thresholds: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [f"threshold {index} must be positive" for index, row in enumerate(thresholds) if float(row.get("threshold", 0)) <= 0]
    return {"status": "passed" if not errors else "failed", "errors": errors}


def calculate_time_to_threshold(series: pd.DataFrame, threshold: float) -> float | None:
    exceeded = series[series["outlet_flow_cms"] >= threshold]
    if exceeded.empty:
        return None
    return float((pd.to_datetime(exceeded["valid_time"].iloc[0]) - pd.to_datetime(series["issue_time"].iloc[0])).total_seconds() / 3600)


def calculate_duration_above_threshold(series: pd.DataFrame, threshold: float) -> float:
    return float((series["outlet_flow_cms"] >= threshold).sum() * series["interval_minutes"].iloc[0] / 60)


def calculate_threshold_exceedance(series: pd.DataFrame, thresholds: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{"threshold_name": row["name"], "threshold": row["threshold"], "time_to_threshold_hr": calculate_time_to_threshold(series, row["threshold"]), "duration_above_threshold_hr": calculate_duration_above_threshold(series, row["threshold"]), "threshold_source": row.get("source", "user_config")} for row in thresholds])


def calculate_threshold_exceedance_probability(ensemble: pd.DataFrame, thresholds: list[dict[str, Any]]) -> pd.DataFrame:
    return calculate_exceedance_probability(ensemble, thresholds)


def write_uncertainty_report(output_dir: str | Path, result: dict[str, pd.DataFrame]) -> dict[str, Path]:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, frame in result.items():
        path = root / f"{name}.xlsx"
        frame.to_excel(path, index=False)
        paths[name] = path
    report = root / "forecast_uncertainty_report.md"
    report.write_text("# Forecast uncertainty\n\nThis output is a scenario ensemble. Member fractions are not formal probabilities.\n", encoding="utf-8")
    paths["report"] = report
    return paths
